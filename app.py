# SPDX-License-Identifier: MIT
"""Main application class for PA Simulator."""

import copy
import os
import json
import pygame
from pathlib import Path
from win32 import win32gui
import keyboard
import time
from typing import Dict, Any, Optional

from constants import DEBUG_PANEL_HEIGHT, FRAME_RATE, KEY_REPEAT_DELAY, TIME_SCALE
from audio import AudioPlayer
from displays.base import ChangeScheduler
from displays.train_models import get_train_model
from displays.utils import draw_text
import i18n
import tims.band as status_band
import window_utils


class AppState:
    """Holds the current state of the application."""

    # CONTRACT: Layer 1 (App) state machine cycles APPROACHING_EARLY → APPROACHING_FINAL → STOPPING per stop.
    # See DISPLAY.md § "Unified State Machine" for transitions; § "Edge cases & guards" for non-obvious behavior.
    # Non-obvious field semantics:
    #   cnt_pa — DEAD during STOPPING (at_station overrides prefix; cnt_pa is not read until _advance_to_next_stop).
    #   cnt_pa_at_station — `-1` is the pre-first sentinel ("next press plays [0]").
    #   frame_mode — read by lower_lcd as an early-return gate; never mutated. Dormant scaffolding.

    def __init__(self):
        """Initialize application state."""
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_sta = 0
        self.circular = 0
        self.skip = 0
        self.frame_mode = 1
        self.departure_time = 0.0  # Timestamp when train departed for current segment
        self.is_last_pa = False  # Whether current PA is the last one before arriving
        # Time-based skip progression. cursor_pos derives from these.
        self.time_to_next = 0  # Time from current to next stopping station
        self.skip_progress = 0  # Passing-station ticks completed (0..skip)
        # STOPPING state — train is at the platform (between arrival and next departure).
        # Boots True so curr_stop=0 starts in STOPPING (the train is parked at the start
        # platform, no advance-into has happened). cnt_pa_at_station = -1 means "no
        # at-station PA played yet, next press plays pa_at_station[0]" — mirrors how
        # cnt_pa=0 means "pa[0] just played" (so -1 is the pre-first sentinel).
        self.at_station = True
        self.cnt_pa_at_station = -1

    @property
    def cursor_pos(self) -> int:
        """Visual cursor position on the lower-LCD route map.

        Equals ``curr_stop`` except during skip animation, when the cursor
        lags behind by ``skip - skip_progress`` and walks forward as time
        passes (or a PA-within-stop tick fires) until it catches up.
        """
        return self.curr_stop - max(0, self.skip - self.skip_progress)

    # CONTRACT: skip-animation state owner — renderer stays pure.
    # See DISPLAY.md § "Station Skip Logic (full spec)".
    # Wrong: mutating skip from the renderer. Right: bump skip_progress here; cursor_pos auto-derives.
    def update_skip_progress(self, current_time: float) -> None:
        """Advance ``skip_progress`` through passing stations based on elapsed time.

        ``cursor_pos`` derives from ``curr_stop - (skip - skip_progress)`` —
        bumping ``skip_progress`` here is what pulls the visual cursor forward.

        Called from the main loop before each frame's draw. State-machine
        logic; lives on AppState rather than the renderer so the lower
        display can stay pure rendering (mirrors the upper).
        """
        if self.skip == 0:
            return

        # departure_time == 0.0 is the uninitialized sentinel (no skip in flight).
        # current_time is always a real time.time() timestamp from the run loop;
        # no need to guard for current_time <= 0.
        if self.departure_time <= 0:
            return

        if self.time_to_next <= 0:
            return

        elapsed_minutes = (current_time - self.departure_time) / TIME_SCALE

        # Skip stations divide the travel time into (skip + 1) segments.
        # skip=1: 50% mark -> progress to first passing.
        # skip=2: 33% / 67% marks -> first / second passing.
        for i in range(1, self.skip + 1):
            threshold = self.time_to_next * i / (self.skip + 1)
            if elapsed_minutes >= threshold and self.skip_progress < i:
                self.skip_progress = i


class _SilentAudio:
    """No-op audio used in preview mode.

    Drops in for AudioPlayer so preview can step through PA/state logic
    instantly without playing sound, while `_next_pa` / `_next_sta` stay
    unchanged (they only call audio through this interface).
    """

    def play_pa(self, *args, **kwargs) -> None: ...
    def play_pa_at_station(self, *args, **kwargs) -> None: ...
    def play_sta(self, *args, **kwargs) -> None: ...
    def pause(self) -> None: ...
    def pause_pa(self) -> None: ...
    def pause_sta(self) -> None: ...
    def unpause(self) -> None: ...
    def stop(self) -> None: ...
    def stop_sta(self) -> None: ...

    def cut_to_tail(self) -> bool:
        # False = "no tail armed", which is also the truth in preview: nothing plays,
        # so nothing can be cut. _next_sta falls through to its replay path.
        return False

    def is_playing(self) -> bool:
        return False

    def is_pa_playing(self) -> bool:
        return False

    def is_sta_playing(self) -> bool:
        return False

    def is_sta_looping(self) -> bool:
        return False

    def position(self) -> Optional[float]:
        return None

    def duration(self) -> Optional[float]:
        return None

    def cleanup(self) -> None: ...


class PASimulator:
    """Main application class managing game loop and state."""

    def __init__(
        self,
        work_dir: str,
        route_data: Optional[Dict] = None,
        preview: bool = False,
        auto_input: bool = False,
        tutorial: bool = False,
        target_surface: Optional[pygame.Surface] = None,
        model: Optional[str] = None,
    ):
        """Initialize the PA Simulator.

        Args:
            work_dir: Directory containing the route.json and audio folders
            route_data: Optional pre-loaded route data dictionary
            preview: If True, run with silent audio and pygame-event input
                (used by preview_display.py). Swap inventory:
                  - ``AudioPlayer`` → ``_SilentAudio`` (no-op stub above; PA/STA
                    methods exist but play nothing).
                  - ``keyboard``-library polling → ``_handle_input_preview``
                    (pygame.KEYDOWN events, dispatched in the run loop).
                  - ``pygame.mixer.init()`` skipped in ``_init_pygame`` (no
                    audio device touched).
                  - ``win32gui.SetWindowPos`` skipped in ``_init_pygame`` (the
                    hard-pinned position is real-app-only; preview uses pygame
                    default placement).
                Everything else — route loading, ``_next_pa`` / ``_next_sta``,
                state machine, draw loop — is shared with the real app, so
                state-machine fixes apply to preview without porting.
            auto_input: If True, allocate an extra DEBUG_PANEL_HEIGHT row above
                the LCD for the auto-input debug panel. The LCD code is unchanged
                — it draws to a sub-surface positioned below the panel and is
                unaware of the offset. Populated by `auto_input.AutoDriver` via
                `self.auto_input_status` dict.
            tutorial: If True, the simulator runs as an embedded LCD inside
                the OOBE tutorial's larger window (1100×500). Caller (tutorial.py)
                creates the display + supplies ``target_surface`` (the LCD
                sub-surface). Skips ``pygame.display.set_mode``, the win32 window
                pin, and the caption set; uses real ``AudioPlayer`` for live audio.
                Tutorial drives the sim via direct method calls (``_next_pa`` /
                ``_next_sta`` / ``jump_to_stop``) and ticks the render path
                manually each frame — does NOT call ``run()``.
            target_surface: Pre-allocated LCD render target. Required when
                ``tutorial=True``; ignored otherwise.
            model: Train-display model key (e.g. "e235_0"). Selects the
                upper/lower display classes + window dimensions via the
                registry in ``displays/train_models/__init__.py``. Sourced
                from the setup-screen picker (seeded by the route's default);
                ``None`` / unknown falls back to the default model.
        """
        self.preview = preview
        self.auto_input = auto_input
        self.tutorial = tutorial
        self.target_surface = target_surface
        self.work_dir = work_dir
        self.route_data = route_data
        # Resolve the train-display model before _init_pygame (it needs the
        # model's window dims) and the display instances below.
        self._train_model = get_train_model(model)
        self._load_route_data()
        self._init_pygame()

        # Initialize state
        self.state = AppState()
        self.state.circular = 1 if (self.stops and self.stops[0].get("name") == self.stops[-1].get("name")) else 0

        # Index of the route's destination within the stops list. For
        # non-circular routes, this is where the train terminates — stops
        # past this index (e.g. Keihin 727B's data extends from 磯子 to 大船
        # for through-running reference) should NOT be advanced into.
        # Circular routes intentionally don't use this — they have stop-level
        # dest cycling and the loop-back branch in _next_pa, so a duplicate
        # name match (first vs last station of a loop) here is harmless.
        self.dest_stop_idx = next(
            (i for i, s in enumerate(self.stops) if s.get("name") == self.dest),
            len(self.stops) - 1,
        )

        # Initialize components
        self.audio = _SilentAudio() if preview else AudioPlayer(self.audio_root, self.stops)
        self.upper = self._train_model.upper_cls(self.screen, self.route_data, self.stops, audio=self.audio)
        # Lower shares the upper's mode_cycler — modes stay in lockstep, no
        # parallel timer. set_state below binds the state reference; lower
        # reads cursor_pos / skip / etc. live from it each frame.
        self.lower = self._train_model.lower_cls(self.screen, self.route_data, self.stops, self.upper.mode_cycler)
        self.lower.set_state(self.state)
        # Single owner of every discrete view change (language flip + slot
        # rotation), enforcing the anti-flash floor across both. Neither
        # display ticks itself — see displays/base.py ChangeScheduler.
        self.scheduler = ChangeScheduler(self.upper.mode_cycler, self.lower)

        self.running = True

        # How run() exits: "quit" (window close / ESC → full app exit) or "home" (band Home
        # pressed → stop PA + return to the setup screen). main.py reads the return of run().
        self.exit_action: str = "quit"

        # {home/save/pause: Rect} from the status band's last render — the run-loop click handler
        # hit-tests against these. Empty until the first _render_panel (boot draw sets it).
        self._band_hits: dict = {}

        # Set by an external auto-input driver (auto_input.AutoDriver running in a
        # background thread) to request a PA fire from the main thread. The input
        # loop checks this alongside keyboard.is_pressed("page down") and resets
        # to False after firing — so auto-fires take the same code path as manual
        # PageDown presses. See auto_input/README.md.
        self.pending_next_pa: bool = False

        # Page Up is EDGE-triggered, unlike Page Down / End which are level-triggered
        # with a wait() throttle. `_next_sta` picks its branch from playback state, so a
        # level-triggered poll turns ONE physical press into two actions: poll 1 starts
        # the melody, poll 2 (~33ms later at 30fps, key still down) sees it playing and
        # takes the second branch. Loading a track takes ~155ms and a keypress runs
        # 80-200ms, so it fired on roughly half of presses. Reported as "the melody
        # sometimes won't replay from the head" — before the loop redesign the second
        # branch restarted at sta_cut, so a press meant to replay landed on the
        # closing-door announcement instead. It survives the redesign unchanged: poll 2
        # now sees `is_sta_looping()` and cuts. A throttle would only narrow the window;
        # both branch rules mean "press AGAIN", so the edge is the thing to test. Page
        # Down keeps its level-trigger deliberately — held-key self-retry is what
        # `pending_next_pa` relies on.
        self._pageup_was_down: bool = False

        # Set by _handle_lcd_click on a successful click-jump. A click-jump is
        # Layer-1-authoritative (user intent): App jumps to STOPPING@curr_stop.
        # The auto-input driver consumes this single-shot flag to re-anchor its
        # Layer 2 belief to that position. Harmless when auto_input is off —
        # nobody consumes it. See auto_input/README.md § "When layers diverge".
        self.click_jump_pending: bool = False

        # Set by the AutoDriver (_maybe_reentry) when the game has moved on but
        # the app is still parked (Layer 3 → Layer 1 re-entry catch-up). Single-
        # shot: "1A" or "1B" — the APPROACHING sub-state to silently advance into.
        # Consumed on the main thread in _handle_input_main (AppState is mutated
        # only there, never from the OCR thread). Harmless when auto_input is off.
        # See auto_input/README.md § "When layers diverge".
        self.pending_silent_advance: Optional[str] = None

        # Latest OCR readings + detector state, written by AutoDriver thread, read
        # by the debug panel on the main thread. Atomic dict assignment in CPython.
        # Empty dict means "no data yet" — the panel renders a placeholder.
        self.auto_input_status: dict = {}

        # Path to the live drive blackbox JSONL (set by AutoDriver when it opens
        # a per-session log). Read by the debug-bar Report button to know which
        # log to render an HTML drive report from.
        self.drive_log_path: Optional[Path] = None

        # Reference to the AutoDriver instance, stashed by main.py so the debug-
        # panel click handler can toggle pause/resume. None when auto_input=False.
        self.auto_driver: Optional[Any] = None

    def _load_route_data(self) -> None:
        """Load route.json configuration via the route_loader module.

        Loader-time computations (dest closure, station translation merge,
        dest_furigana lookup) live in ``route_loader.finalize_route``; this
        method just plumbs the result onto the simulator.
        """
        from route_loader import finalize_route, load_route_from_dir, resolve_audio_root

        self.station_db = self._load_station_db()

        if self.route_data is None:
            self.route_data = load_route_from_dir(self.work_dir, self.station_db)
        else:
            self.route_data = finalize_route(self.route_data, self.station_db)

        self.stops = self.route_data.get("stops", [])
        # Single resolved audio root — route folder, or the per-line shared
        # pool when route.json declares audio_root. See route_loader CONTRACT.
        self.audio_root = str(resolve_audio_root(self.work_dir, self.route_data))
        self.route_name = self.route_data.get("route", "Unknown")
        self.train_type = self.route_data.get("type", "")
        self.dest = self.route_data.get("dest", "")
        self.dest_furigana = self.route_data.get("dest_furigana", "")

        self.color = self.route_data.get("color", [255, 255, 255])
        self.contrast_color = self.route_data.get("contrast_color", [224, 54, 37])
        self.type_color = self.route_data.get("type_color", [0, 0, 0])

    def _load_station_db(self) -> Dict:
        """Load central translations.json from data/ directory.

        Returns empty dict if not found.
        """
        from app_paths import project_root

        translations_path = project_root() / "data" / "translations.json"

        if os.path.exists(translations_path):
            with open(translations_path, encoding="utf-8") as f:
                return json.load(f)

        return {}

    def _init_pygame(self) -> None:
        """Initialize pygame display.

        When ``auto_input`` is True, the window is taller by ``DEBUG_PANEL_HEIGHT``
        and ``self.screen`` is a sub-surface positioned below the panel area —
        existing LCD code is oblivious to the offset. ``self.debug_surface`` is
        the panel's own sub-surface (None when auto-input is off).

        When ``tutorial`` is True, ``self.screen`` is the caller-provided
        ``target_surface`` (a sub-surface inside the tutorial's 1100×500
        window). We do NOT call ``set_mode`` (would resize the tutorial
        window), do NOT pin a window position, and do NOT re-init the mixer
        (caller has already initialized it via main.py at startup).
        """
        # Idempotent and one-way. main.py already declares it before the setup flow; repeating it
        # here covers every entry point that builds a PASimulator directly (preview_display.py and
        # the other harnesses), which would otherwise read pygame.display.Info() as the VIRTUALIZED
        # desktop — 1536x864 on a 125% 1080p screen — and pick a zoom off the wrong numbers. It also
        # keeps preview fidelity honest: calibration should be judged in the frame that ships.
        window_utils.declare_dpi_awareness()
        pygame.init()
        if self.tutorial:
            # Caller owns the display + mixer; just bind our render target.
            self.clock = pygame.time.Clock()
            self.window = pygame.display.get_surface()
            self.screen = self.target_surface
            self.debug_surface: Optional[pygame.Surface] = None
            self.canvas = self.target_surface  # no zoom in the tutorial; caller sized the window
            self.zoom = 1
            return
        if not self.preview:
            pygame.mixer.init()
        self.clock = pygame.time.Clock()
        s_width, s_height = self._train_model.s_width, self._train_model.s_height
        panel_h = DEBUG_PANEL_HEIGHT if self.auto_input else 0

        # Renderers draw into an OFFSCREEN canvas at native size and never learn about zoom; the
        # window is a scaled presentation of it (_present). Keeping them separate is what lets the
        # window resize without touching a single renderer or a single calibrated coordinate.
        self.canvas = pygame.Surface((s_width, s_height + panel_h))
        if self.auto_input:
            self.debug_surface = self.canvas.subsurface((0, 0, s_width, panel_h))
            self.screen = self.canvas.subsurface((0, panel_h, s_width, s_height))
        else:
            self.debug_surface = None
            self.screen = self.canvas

        info = pygame.display.Info()
        cw, ch = self.canvas.get_size()
        work_w, work_h = window_utils.work_area(info.current_w, info.current_h)
        self._max_zoom = window_utils.max_zoom(cw, ch, work_w, work_h)
        saved = i18n.load_settings().get("window_zoom")
        if isinstance(saved, int) and 1 <= saved <= self._max_zoom:
            self.zoom = saved  # a size the user chose deliberately outranks the default
        else:
            self.zoom = window_utils.pick_default_zoom(cw, ch, work_w, work_h)
        self.window = pygame.display.set_mode((cw * self.zoom, ch * self.zoom), pygame.RESIZABLE)
        pygame.display.set_caption("PIDS Preview  —  PageDown=PA  PageUp=Mode  ←/→=Jump  ESC=Quit" if self.preview else "PA Simulator")

        if not self.preview:
            # Set window position (real app only; preview uses default placement)
            try:
                info = pygame.display.get_wm_info()
                win32gui.SetWindowPos(info["window"], -1, s_width, s_height, 0, 0, 1)
            except Exception as e:
                print(f"Warning: Could not set window position: {e}")

    def run(self) -> None:
        """Main game loop."""
        # Boot lands in STOPPING@curr_stop=0 by default (see AppState.__init__);
        # prefix reads "ただいま <start station>".
        #
        # CONTRACT: boot MUST seed the scheduler with real wall-clock, and pass
        # the same value to lower.draw(). Seeding at 0.0 makes the first
        # main-loop tick see a huge delta against every timer and instant-fire a
        # change — the boot view never persists through its natural duration.
        # Surfaced 2026-05-07 via `preview --lower-view full` opening in the
        # 8-station view.
        boot_t = time.time()
        self.scheduler.seed(boot_t)
        self.upper.set_state(
            self.state.curr_stop, self.state.cnt_pa, at_station=self.state.at_station, cnt_pa_at_station=self.state.cnt_pa_at_station
        )
        self.upper.draw()
        self.lower.draw(boot_t)
        self._render_panel()
        self._present()

        while self.running:
            self.clock.tick(FRAME_RATE)
            timestamp = time.time()

            # Advance skip animation (was inside LowerDisplay; moved here so
            # the display layer stays pure-rendering, mirroring upper).
            self.state.update_skip_progress(timestamp)

            # One atomic tick for every discrete change (language flip, slot
            # rotation, frame swap). MUST run after update_skip_progress — slot
            # membership reads cursor_pos — and before both draws, which are
            # pure renderers.
            self.scheduler.tick(timestamp, self.state)

            self.upper.draw(time.strftime("%H:%M", time.localtime(timestamp)))

            # Draw lower display with current time for real-time countdown
            self.lower.draw(timestamp)

            self._render_panel()

            self._present()

            # Handle input
            self._handle_input()
            self._update_hover_cursor()

            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    # Snap the dragged size to a whole multiple so the blit stays nearest-neighbour.
                    # The window visibly sticks at each multiple — that IS the affordance telling the
                    # user which sizes are sharp, with no settings dialog to find.
                    self._apply_zoom(window_utils.snap_zoom(self.canvas.get_height(), event.h, self._max_zoom))
                elif (
                    event.type == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and self.auto_input
                    and self.debug_surface is not None
                    and self.window_to_canvas(event.pos)[1] < self.debug_surface.get_height()
                ):
                    # Click inside the status band → its control cluster (pause / save / home).
                    self._handle_band_click(self.window_to_canvas(event.pos))
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # Click below the debug panel (or anywhere when no panel)
                    # — try click-to-jump on the lower LCD.
                    self._handle_lcd_click(event.pos)

        # "home" keeps pygame/font/mixer alive so main.py can re-enter setup; "quit" tears it all down.
        self.cleanup(full_quit=(self.exit_action != "home"))
        return self.exit_action

    def _render_panel(self) -> None:
        """Hand the debug sub-surface to the TIMS status band for rendering.

        PASimulator owns the window allocation; ``status_band`` owns all panel
        rendering (layout, fonts, colors) — same hand-off contract the retired
        debug panel had, now the shared band. The band's returned
        {home/save/pause} hit-rects are stashed for the run-loop click handler.
        No-op when auto_input is off.
        """
        if not self.auto_input or self.debug_surface is None:
            return
        status_band.ACTIVE_LANG = i18n.current_lang()  # band chrome follows the user's UI language
        self._band_hits = status_band.render(
            self.debug_surface, status=self.auto_input_status, sim_state=self.state, stops=self.stops, save_notice=getattr(self, "last_save", None)
        )

    def _handle_band_click(self, pos) -> None:
        """Dispatch a click inside the status band's control cluster (hit-rects from the last render):
        Pause toggles the auto-driver, Save generates the drive report, Home stops PA + returns to the
        setup screen (run() exits "home" → main.py re-shows setup).

        ``pos`` is in CANVAS coordinates — the caller applies ``window_to_canvas`` first, because the
        band's hit-rects come from rendering into the canvas and know nothing about window zoom."""
        hits = self._band_hits
        home, pause, save = hits.get("home"), hits.get("pause"), hits.get("save")
        if home is not None and home.collidepoint(pos):
            status_band.press_flash(self.debug_surface, home, "home")
            self.exit_action = "home"
            self.running = False
        elif pause is not None and pause.collidepoint(pos):
            driver = self.auto_driver
            # Flash the CURRENTLY-shown label (the toggle's pre-click state): "繼續/Play" when
            # already paused, "暫停/Pause" when running.
            status_band.press_flash(self.debug_surface, pause, "resume" if (driver is not None and driver.paused) else "pause")
            if driver is not None:
                driver.paused = not driver.paused
                print(f"[AutoDriver] {'paused' if driver.paused else 'resumed'} via band button")
        elif save is not None and save.collidepoint(pos):
            status_band.press_flash(self.debug_surface, save, "save")
            from auto_input import generate_report  # local import: defer dxcam pull

            generate_report(self)

    # ──────────────────────────── input handling ────────────────────────────
    def _click_target(self, lcd_x: int, lcd_y: int) -> Optional[int]:
        """Return the sim_index a click at (lcd_x, lcd_y) would jump to, or None.

        Coords are LCD-local (debug-panel offset already subtracted). Layers
        the past-dest filter on top of the renderer's hit_test — cells past
        ``dest_stop_idx`` on non-circular routes are not clickable (e.g.
        Keihin 727B's 磯子→大船 reference tail).
        """
        sim_idx = self.lower.hit_test(lcd_x, lcd_y)
        if sim_idx is None:
            return None
        if self.state.circular != 1 and sim_idx > self.dest_stop_idx:
            return None
        return sim_idx

    def window_to_canvas(self, pos) -> tuple[int, int]:
        """Map WINDOW coordinates to CANVAS coordinates by undoing the zoom.

        # CONTRACT: the single window->canvas transform. Every consumer of mouse position goes
        # through this or through window_to_lcd, which is built on it — never re-derive inline.
        # See issue #73: a wrong transform makes click-to-jump land on the WRONG station, and a
        # wrong station is still a valid jump, so nothing anywhere raises an error.
        """
        return pos[0] // self.zoom, pos[1] // self.zoom

    def window_to_lcd(self, pos) -> Optional[tuple[int, int]]:
        """Map WINDOW coordinates to LCD-local coordinates, or None if the point is outside the LCD.

        Two terms: undo the zoom, then subtract the status-band offset (present when auto_input is
        on). Order matters — the band's height is a CANVAS measurement, so the zoom has to come off
        first or the offset is applied in the wrong unit.
        """
        cx, cy = self.window_to_canvas(pos)
        panel_h = self.debug_surface.get_height() if (self.auto_input and self.debug_surface is not None) else 0
        lcd_y = cy - panel_h
        if lcd_y < 0:
            return None
        return cx, lcd_y

    def _present(self) -> None:
        """Blit the offscreen canvas to the window and flip.

        Nearest-neighbour by construction: the window is only ever an exact whole multiple of the
        canvas (window_utils.snap_zoom), so ``scale`` maps each source pixel to a clean k*k block
        with no interpolation. ``scale`` writing straight into the window surface avoids a second
        temporary each frame.
        """
        if self.zoom == 1:
            self.window.blit(self.canvas, (0, 0))
        else:
            pygame.transform.scale(self.canvas, self.window.get_size(), self.window)
        pygame.display.flip()

    def _apply_zoom(self, k: int) -> None:
        """Adopt whole-multiple ``k``: force the window to exactly k*canvas and remember the choice.

        The guard is the WINDOW SIZE, not k. A drag that snaps back to the same multiple still
        leaves the OS window at whatever odd size the user released at, and returning early there
        would leave every later frame nearest-scaling the canvas into a non-multiple — permanently
        uneven pixels, which is the exact thing whole-multiple snapping exists to prevent.

        It is also the loop terminator: ``set_mode`` emits another resize event, that event snaps to
        the same k, and this time the size already matches so it returns.
        """
        k = max(1, min(self._max_zoom, k))
        cw, ch = self.canvas.get_size()
        target = (cw * k, ch * k)
        if k == self.zoom and self.window.get_size() == target:
            return
        changed = k != self.zoom
        self.zoom = k
        self.window = pygame.display.set_mode(target, pygame.RESIZABLE)
        if changed:  # only a deliberate zoom change is worth a settings write
            settings = i18n.load_settings()
            settings["window_zoom"] = k
            i18n.save_settings(settings)

    def _handle_lcd_click(self, pos) -> None:
        """Translate a window-coords click into a click-to-jump action.

        Silent no-op outside the LCD region or on non-clickable cells.
        """
        lcd = self.window_to_lcd(pos)
        if lcd is None:
            return
        mx, lcd_y = lcd
        sim_idx = self._click_target(mx, lcd_y)
        if sim_idx is None:
            return
        self.jump_to_stop(sim_idx)
        # Click-jump is Layer-1-authoritative; signal the auto-driver to
        # re-anchor its Layer 2 belief to the new STOPPING@curr_stop.
        self.click_jump_pending = True

    def _update_hover_cursor(self) -> None:
        """Set pointer-hand cursor over clickable cells, default elsewhere."""
        lcd = self.window_to_lcd(pygame.mouse.get_pos())
        clickable = lcd is not None and self._click_target(*lcd) is not None
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if clickable else pygame.SYSTEM_CURSOR_ARROW)

    def _handle_input(self) -> None:
        """Dispatch input handling based on mode.

        Tutorial mode never goes through ``run()`` (the tutorial drives the
        sim manually via direct method calls), so this should never be invoked
        in tutorial mode. Defensive guard catches misuse — without it, the
        global ``keyboard`` library polling in ``_handle_input_main`` would
        bypass the tutorial's action lock-down.
        """
        if self.tutorial:
            return
        if self.preview:
            self._handle_input_preview()
        else:
            self._handle_input_main()

    def _handle_input_main(self) -> None:
        """Real app: global keyboard polling via `keyboard` library.

        ``pending_next_pa`` is checked alongside the manual PageDown — an
        auto-input driver running in a background thread sets it to fire a PA
        through the same code path. See auto_input/README.md.
        """
        try:
            # Sample Page Up ONCE per frame and derive the press EDGE. Must run every
            # frame, including frames where a branch below never looks at it, or the
            # flag never clears on release and the next press is swallowed.
            pageup_down = keyboard.is_pressed("page_up")
            pageup_edge = pageup_down and not self._pageup_was_down
            self._pageup_was_down = pageup_down

            # Re-entry silent advance (AutoDriver Layer 3 → Layer 1 catch-up).
            # Single-shot signal from the OCR thread; consumed here so AppState
            # mutation stays on the main thread. No audio, no failing precondition
            # — consume immediately (same pattern as the click-jump re-anchor).
            if self.pending_silent_advance is not None:
                target = self.pending_silent_advance
                self.pending_silent_advance = None
                self._silent_advance_to(target)
            # Gate consumption on audio: `_next_pa` no-ops while a PA is mid-play
            # (PA-blocks-PA, line 599). Without this gate, an auto-fire's
            # single-shot `pending_next_pa` would be reset before _next_pa got a
            # chance to act — silently dropping the at-station press if the long
            # まもなく PA was still playing. Held-key manual press self-retries
            # via the next frame; pending_next_pa needs the same retry behavior.
            if (keyboard.is_pressed("page down") or self.pending_next_pa) and not self.audio.is_pa_playing():
                self.pending_next_pa = False
                self._next_pa()
                pygame.time.wait(KEY_REPEAT_DELAY)
            elif pageup_down:
                # Still gated on the key being DOWN so a held Page Up keeps blocking the
                # End branch exactly as before; only the ACTION moved to the edge.
                if pageup_edge:
                    self._next_sta()
            elif keyboard.is_pressed("end") and self.audio.is_playing():
                # When both PA + STA overlap, pause STA preferentially —
                # the in-train PA carries info, the platform melody is the
                # one users typically want to silence.
                if self.audio.is_sta_playing():
                    self.audio.pause_sta()
                else:
                    self.audio.pause_pa()
                # Throttle: End is stateful (each press changes which stream
                # is paused) so frame-rate polling without a delay would
                # collapse a single tap into "pause STA then pause PA" on
                # consecutive frames.
                pygame.time.wait(KEY_REPEAT_DELAY)
        except Exception as e:
            print(f"Input error: {e}")

    def _handle_input_preview(self) -> None:
        """Preview: focus-based pygame events. Also drains the event queue
        (including QUIT), so run()'s own event loop sees nothing and is a no-op
        in preview mode."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_PAGEDOWN:
                    self._next_pa()
                elif event.key == pygame.K_PAGEUP:
                    self._next_sta()
                elif event.key == pygame.K_RIGHT:
                    self.jump_to_stop(self.state.curr_stop + 1)
                elif event.key == pygame.K_LEFT:
                    self.jump_to_stop(self.state.curr_stop - 1)
                elif event.key == pygame.K_m:
                    self._cycle_display_mode()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_lcd_click(event.pos)

    def _cycle_display_mode(self) -> None:
        """Cycle the upper display's forced mode (preview helper, bound to M)."""
        from displays.base import DisplayMode

        order = [DisplayMode.KANJI, DisplayMode.FURIGANA, DisplayMode.ENGLISH]
        cur = self.upper.mode_cycler.current_mode
        nxt = order[(order.index(cur) + 1) % len(order)]
        self.upper.mode_cycler.current_mode = nxt
        self.upper.mode_cycler.enabled = False

    def jump_to_stop(self, target: int, direction: int = -1) -> None:
        """Hard-jump to a stop index, bypassing PA/audio cycle.

        If ``target`` lands on a passing station (``pa == []``), rolls in
        ``direction`` (-1 backward default, +1 forward) to the nearest station
        the train would actually stop at. Passing stations are not valid
        resting states in the real app — ``_next_pa``'s while-loop skips them
        on every transition — so the preview should not land there either.

        Default is backward so the preview always lands on the stop just
        *before* any upcoming skip: a pre-skip state from which PageDown
        exercises the skip logic. Consequence: the → arrow becomes a no-op
        when the next station is passing — use PageDown to cross the skip.

        Resets animation state so countdown and skip-progress start fresh
        (``departure_time=0`` keeps the lower-LCD countdown frozen until the
        next real PA advance).

        Pauses any in-flight audio so a jump during PA playback gives a
        clean handoff (no stale audio playing over the new state).

        STA is STOPPED rather than paused: a paused loop is suspended, not ended,
        and it belongs to the platform being left behind. Pause is the right verb
        for PA, whose stream is re-loaded wholesale by the next announcement.
        """
        self.audio.pause()
        self.audio.stop_sta()
        if not self.stops:
            return
        target = max(0, min(target, len(self.stops) - 1))

        def _has_pa(i: int) -> bool:
            # A stop is a valid landing target if it has either a pre-arrival
            # sequence (pa) or an at-station sequence (pa_at_station). Stops
            # with both empty are passing stations and should be rolled past.
            return bool(self.stops[i].get("pa")) or bool(self.stops[i].get("pa_at_station"))

        # Special case: target=0 IS the initial-boarding state. Most real routes
        # have `pa: []` at stop 0 because no announcement has played yet (the
        # train is sitting at the start). Don't roll away from it — that's
        # exactly the state the user wants to preview. The lower LCD's special
        # "yellow flag" rendering at curr_stop=0 is meant for this.
        if target == 0:
            pass
        elif not _has_pa(target):
            step = 1 if direction >= 0 else -1
            scan = target
            while 0 <= scan < len(self.stops) and not _has_pa(scan):
                scan += step
            if 0 <= scan < len(self.stops):
                target = scan
            else:
                # Hit the boundary without finding PA — fall back the other way.
                scan = target
                step = -step
                while 0 <= scan < len(self.stops) and not _has_pa(scan):
                    scan += step
                if 0 <= scan < len(self.stops):
                    target = scan
                # else: no stop with PA anywhere — stay on clamped target.

        # Lands in STOPPING@target — the unified model treats jump as
        # "I'm at platform X." Next press cycles pa_at_station (or advances
        # if empty). See DISPLAY.md § "Unified State Machine".
        self.state.curr_stop = target
        self.state.cnt_pa = 0
        self.state.cnt_pa_at_station = -1
        self.state.at_station = True
        self.state.cnt_sta = 0
        self.state.skip = 0
        self.state.skip_progress = 0
        self.state.time_to_next = 0
        self.state.is_last_pa = False
        self.state.departure_time = 0.0
        self.upper.set_state(target, 0, at_station=True, cnt_pa_at_station=self.state.cnt_pa_at_station)

    # CONTRACT: unified state machine cycles APPROACHING -> STOPPING -> APPROACHING.
    # See DISPLAY.md § "Unified State Machine" — entry to STOPPING is a no-audio
    # press; exit from STOPPING is the advance press that plays the next stop's pa[0].
    # CONTRACT: terminus_idx = dest_stop_idx for non-circular routes (NOT
    # len(stops)-1). See DISPLAY.md § "Terminus (`dest_stop_idx`)". Route data
    # may extend past dest for through-running reference (Keihin 727B 磯子→大船).
    def _next_pa(self) -> None:
        """Advance the state machine by one press."""
        # Only PA blocks PA — STA plays on its own channel and does not
        # delay the train's announcement flow (matches IRL: the platform
        # melody and the in-train PA are independent audio sources).
        if self.audio.is_pa_playing():
            return
        if not self.stops:
            return

        if self.state.at_station:
            self._next_in_stopping()
        else:
            self._next_in_approaching()

    def _next_in_stopping(self) -> None:
        """Press while at_station=True.

        Plays the next pa_at_station entry if available; otherwise the press
        becomes the advance press that exits STOPPING and lands in APPROACHING
        at the next stop.
        """
        pa_at_st = self.stops[self.state.curr_stop].get("pa_at_station", [])
        if self.state.cnt_pa_at_station + 1 < len(pa_at_st):
            self.state.cnt_pa_at_station += 1
            self.audio.play_pa_at_station(self.state.curr_stop, self.state.cnt_pa_at_station)
            # Prefix stays "ただいま X", but the yellow hint must refresh so
            # it stops flashing once the last pa_at_station is started.
            self.upper.set_state(self.state.curr_stop, self.state.cnt_pa, at_station=True, cnt_pa_at_station=self.state.cnt_pa_at_station)
            self.upper.draw()
            return
        self._advance_to_next_stop()

    def _next_in_approaching(self) -> None:
        """Press while at_station=False.

        Plays the next pa entry if available; otherwise the press enters
        STOPPING (no audio, prefix flips to "ただいま").
        """
        pa_tracks = self.stops[self.state.curr_stop].get("pa", [])
        if self.state.cnt_pa < len(pa_tracks) - 1:
            # Within-pa: catches the cursor up if a skip animation was still
            # mid-flight (e.g., user pressed PageDown faster than the time
            # threshold). Skip-zeroing is what prevents single-PA-target leakage.
            self.state.cnt_pa += 1
            self.state.is_last_pa = self.state.cnt_pa >= len(pa_tracks) - 1
            self.state.skip = 0
            self.state.skip_progress = 0
            self.state.time_to_next = 0
            self.audio.play_pa(self.state.curr_stop, self.state.cnt_pa)
            self.upper.set_state(self.state.curr_stop, self.state.cnt_pa, at_station=False, cnt_pa_at_station=self.state.cnt_pa_at_station)
            self.upper.draw()
            return
        # pa exhausted — enter STOPPING (no audio).
        self.state.at_station = True
        self.state.cnt_pa_at_station = -1
        self.upper.set_state(self.state.curr_stop, self.state.cnt_pa, at_station=True, cnt_pa_at_station=self.state.cnt_pa_at_station)
        self.upper.draw()

    def _advance_to_next_stop(self, silent: bool = False) -> None:
        """Exit STOPPING@curr_stop and advance to the next stopping station.

        Plays pa[0] of the new stop and lands in APPROACHING. Sets up skip
        animation if passing stations were crossed. Circular routes loop from
        idx N (= last duplicate of start) directly to idx 1 — the duplicate
        idx 0 is just a structural marker for circularity, not a state to visit.

        ``silent=True`` (AutoDriver re-entry catch-up via _silent_advance_to)
        runs all the state-setting logic — passing-station scan, terminus /
        circular guards, skip animation, departure_time — but suppresses the
        pa[0] audio, because on a re-entry the announcement is already stale.
        """
        terminus_idx = (len(self.stops) - 1) if self.state.circular == 1 else self.dest_stop_idx

        def _is_stopping(stop) -> bool:
            return bool(stop.get("pa")) or bool(stop.get("pa_at_station"))

        if self.state.curr_stop < terminus_idx:
            prev_stop = self.state.curr_stop
            self.state.curr_stop += 1
            while self.state.curr_stop <= terminus_idx and not _is_stopping(self.stops[self.state.curr_stop]):
                self.state.curr_stop += 1
            if self.state.curr_stop > terminus_idx:
                # No more stopping stations within terminus — clamp and remain at terminus.
                self.state.curr_stop = terminus_idx
                return
            # cursor_pos starts at (curr_stop - skip), so it appears on the
            # first passing station and walks forward as skip_progress ticks up.
            self.state.skip = self.state.curr_stop - prev_stop - 1
            self.state.skip_progress = 0
            self.state.time_to_next = self.stops[self.state.curr_stop].get("time", 0) if self.state.skip > 0 else 0
        elif self.state.circular == 1:
            # Loop-back: skip the duplicate idx 0 (same name as last stop).
            self.state.curr_stop = 1
            while self.state.curr_stop < len(self.stops) and not _is_stopping(self.stops[self.state.curr_stop]):
                self.state.curr_stop += 1
            self.state.skip = 0
            self.state.skip_progress = 0
            self.state.time_to_next = 0
        else:
            # Non-circular at terminus — no advance possible. Stay in STOPPING.
            return

        self.state.cnt_pa = 0
        self.state.cnt_pa_at_station = -1
        self.state.at_station = False
        self.state.is_last_pa = False
        self.state.departure_time = time.time()
        self.state.cnt_sta = 0
        # Departing kills the melody, and this is the ONE funnel out of STOPPING — the
        # manual Page Down exhaust path and the AutoDriver's silent re-entry catch-up both
        # arrive here. Placed with the other departure resets, BELOW the two guards that
        # return without advancing (the no-more-stopping clamp and the non-circular
        # terminus): on those the train has not left, so the platform melody should not
        # stop. STA-only — the departure fires the next stop's pa[0] on mixer.music below.
        self.audio.stop_sta()
        if not silent:
            self.audio.play_pa(self.state.curr_stop, 0)
        self.upper.set_state(self.state.curr_stop, 0, at_station=False, cnt_pa_at_station=self.state.cnt_pa_at_station)
        self.upper.draw()

    def _silent_advance_to(self, target_state: str) -> None:
        """Re-entry silent advance (no audio): land APPROACHING at the next stop.

        Consumes the AutoDriver's ``pending_silent_advance`` signal — called on
        the MAIN thread (AppState is only ever mutated here, never from the OCR
        thread). ``target_state``:

          - ``"1A"`` (APPROACHING_EARLY) — game CRUISING / PASSING.
          - ``"1B"`` (APPROACHING_FINAL) — game ARRIVING; bumps cnt_pa to the
            last approach PA so the next at-station fire is correctly gated.

        No audio: the departure / approach announcements are stale on a re-entry
        (train already left / is already arriving). See auto_input/README.md
        § "Re-entry (Layer 3 → Layer 2 reconciliation)". Lockstep ±1: advances
        one stop; a cold boot multiple stops behind needs a click-jump first.
        """
        self._advance_to_next_stop(silent=True)
        if target_state == "1B":
            pa = self.stops[self.state.curr_stop].get("pa", [])
            self.state.cnt_pa = max(0, len(pa) - 1)
            self.state.is_last_pa = self.state.cnt_pa >= len(pa) - 1
            self.upper.set_state(self.state.curr_stop, self.state.cnt_pa, at_station=False, cnt_pa_at_station=self.state.cnt_pa_at_station)
            self.upper.draw()

    def _next_sta(self) -> None:
        """Play the station melody, modelling the real platform.

        The LAST sta track is the departure melody: it plays from the head and loops
        ``[0, sta_cut)`` until the user cuts it or departs, exactly as the melody
        runs on a platform until the conductor cuts it. A press while it loops IS
        that cut — jump to `sta_cut` and play the closing announcement once.

        Every OTHER track plays straight through, once. `sta_cut` does not apply to
        them at all; it is a property of the last track, not of the stop (only one
        stop in the corpus has more than one track — saikyo 大宮, whose first entry
        is an arrival door-opening announcement played at the platform).

        `cnt_sta` walks forward and SATURATES at the last index, which is what makes
        the whole model fall out of one discriminator: on a single-track stop it
        never leaves 0, so every press is "the last track".
        """
        if not self.stops:
            return

        current_stop_data = self.stops[self.state.curr_stop]
        sta_tracks = current_stop_data.get("sta", [])

        # Handle empty station melody list
        if not sta_tracks or sta_tracks == [""]:
            return

        cut_position = current_stop_data.get("sta_cut", 0)
        is_last = self.state.cnt_sta >= len(sta_tracks) - 1

        # A press while the melody is LOOPING is the conductor's cut. Gated on the
        # loop itself, not on `is_last and is_sta_playing()` — those come apart on a
        # multi-track stop, where playing the non-last track advances cnt_sta to the
        # last index while that track is still sounding, so the next press would cut
        # a melody that had never started.
        if self.audio.is_sta_looping():
            if self.audio.cut_to_tail():
                return
            # NOTE: deliberately unreachable today — `is_sta_looping()` is only true when
            # `_load_and_play_sta` armed the loop, and that same block is the only place a
            # tail is built, so a running loop always has one. (A stop with an absent or
            # out-of-range sta_cut never arms the loop at all, so it does not reach here.)
            # Kept as belt-and-braces against a future path that arms a loop without a
            # tail: falling through replays rather than swallowing the press.

        self.audio.play_sta(self.state.curr_stop, self.state.cnt_sta, cut_position if is_last else 0, loop=is_last)

        if self.state.cnt_sta < len(sta_tracks) - 1:
            self.state.cnt_sta += 1

    # CONTRACT: snapshot/restore is for the OOBE tutorial's [Back] button + the
    # progress-bar's backward-jump path. AppState fields are scalar-only
    # (verified) so shallow copy via copy.copy() is sufficient; restore via
    # __dict__.update() preserves the @property `cursor_pos` (which lives on
    # the class, not the instance). Caller is responsible for resyncing
    # other sim-side state (audio, upper LCD's set_state) on restore.
    def snapshot_state(self) -> AppState:
        """Snapshot AppState for tutorial [Back] navigation.

        Returns a shallow copy. Caller is responsible for re-syncing other
        sim-side state (audio, upper LCD's set_state) on restore.
        """
        return copy.copy(self.state)

    def restore_state(self, snap: AppState) -> None:
        """Restore an AppState snapshot taken by snapshot_state().

        Pauses in-flight audio (tutorial convention: state jumps pause, not
        stop — silences the soundtrack but keeps the mixer warm) and re-sends
        the upper LCD's set_state so its cached state matches the restored
        AppState. Lower LCD reads state live from self.state each frame, so
        no explicit re-bind is needed there.
        """
        self.audio.pause()
        self.state.__dict__.update(snap.__dict__)
        self.upper.set_state(
            self.state.curr_stop, self.state.cnt_pa, at_station=self.state.at_station, cnt_pa_at_station=self.state.cnt_pa_at_station
        )

    def cleanup(self, full_quit: bool = True) -> None:
        """Clean up resources. ``full_quit`` True → pygame.quit() (full app exit). False → tear down
        only the drive window (pygame.display.quit()), keeping pygame / fonts / mixer alive so the
        caller can re-enter the setup screen (the band Home path)."""
        if hasattr(self, "audio"):
            self.audio.cleanup()
        if full_quit:
            pygame.quit()
        else:
            pygame.display.quit()

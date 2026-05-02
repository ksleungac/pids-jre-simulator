"""Setup screen for route and train selection."""

import os
import json
import pygame

import i18n
from constants import SETUP_KEY_REPEAT_DELAY, SETUP_KEY_REPEAT_INTERVAL
from displays.utils import draw_station_code_badge


class SetupScreen:
    """Handles route and train selection before starting the simulator."""

    def __init__(self, screen: pygame.Surface, show_tutorial_button: bool = False):
        """Initialize the setup screen.

        Args:
            screen: Pygame surface to draw on
            show_tutorial_button: If True, render a "? Tutorial" button in the
                top-right corner that returns the run-tutorial sentinel from
                ``run()``. Caller (main.py) gates this on ``oobe_completed``
                — first-launch users haven't seen the tutorial yet, so the
                button is hidden until they finish (or skip) it.
        """
        self.screen = screen
        self.show_tutorial_button = show_tutorial_button
        self.routes = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.row_height = 50
        self._tutorial_btn_rect: pygame.Rect | None = None
        # Reserve ~60px below the route list for the OCR Auto-PA band, plus the usual
        # title (50px) and instructions (50px). Route list shrinks from 6 to 5 visible
        # rows on the default 420px-tall window.
        available_height = screen.get_height() - 160
        self.max_visible = max(3, available_height // self.row_height)

        # Chrome fonts via i18n.font() — bundled HelveticaNeue on EN (PIDS-canon
        # Latin, clean macron rendering for Tōkyō/Chūō; deterministic across
        # systems), YaHei (SysFont) on HK/CN. `route_font_cjk` is pinned to a
        # CJK language explicitly because route names on line 1 are Japanese
        # kanji today (translation deferred); used for the kanji portion of
        # line 1 in EN mode (two-pass with tail Latin).
        self.title_font = i18n.font(28, bold=True)
        self.route_font = i18n.font(18, bold=True)
        self.instruction_font = i18n.font(16, bold=True)
        self.control_font = i18n.font(14, bold=True)
        self.route_font_cjk = i18n.font_for_lang("zh_HK", 18, bold=True)
        # Line badge re-uses NeueFrutigerWorld-Bold (PIDS-canon, same font as the
        # LCD's station-code badges) for visual consistency with the LCD.
        self.badge_font = pygame.font.Font(str(i18n.app_root() / "fonts" / "NeueFrutigerWorld-Bold.otf"), 18)

        # Translation tables for EN mode lookup of route-level data fields.
        # zh_HK / zh_CN modes keep route-data text in kanji (no source data exists
        # today); only the chrome strings around it translate.
        self._translations = self._load_data_json("translations.json")
        self._train_types = self._load_data_json("train_types.json")

        # Colors — lifted dark slate. Bright enough to read comfortably without
        # going full light mode; controls keep ~20-RGB-step contrast above bg
        # so steppers / pill stay distinct. Highlight green stays separable on
        # luminance for red-green color-blind viewers (not just hue).
        self.bg_color = (62, 68, 80)
        self.text_color = (240, 242, 248)
        self.highlight_color = (96, 168, 84)
        self.dim_color = (175, 182, 195)
        self.highlight_dim_color = (220, 225, 235)  # line-2 dim on highlight bg
        self.control_bg = (88, 96, 112)
        self.control_dim = (118, 126, 142)

        # OCR Auto-PA controls — defaults match the prior CLI defaults; user toggles
        # per-launch (no persistence). Lead/interval clamped to the ranges below.
        self.auto_input_enabled = False
        self.lead_m = 900
        self.interval_s = 5
        self.lead_min, self.lead_max, self.lead_step = 500, 1500, 100
        self.interval_min, self.interval_max, self.interval_step = 1, 10, 1

        # Hit-test rects populated by _draw_auto_pa_band(); read by run() on click.
        self._toggle_rect: pygame.Rect | None = None
        self._lead_minus_rect: pygame.Rect | None = None
        self._lead_plus_rect: pygame.Rect | None = None
        self._interval_minus_rect: pygame.Rect | None = None
        self._interval_plus_rect: pygame.Rect | None = None

    @staticmethod
    def _load_data_json(filename: str) -> dict:
        path = i18n.app_root() / "data" / filename
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def scan_routes(self, base_dir: str = "audio") -> list:
        """Scan for available routes by finding route.json files.

        Groups routes by name, then by train diagram.
        Extracts diagram from folder name when available (e.g., nambu/4027F/route.json).

        Args:
            base_dir: Base directory to scan for routes

        Returns:
            List of route dictionaries
        """
        self.routes = []

        if not os.path.exists(base_dir):
            print(f"Audio directory '{base_dir}' not found")
            return self.routes

        for root, dirs, files in os.walk(base_dir):
            if "route.json" in files:
                route_path = os.path.join(root, "route.json")
                try:
                    with open(route_path, encoding="utf-8") as f:
                        route_data = json.load(f)

                        # Extract diagram from folder name (e.g., "4027F" from "nambu/4027F")
                        rel_path = os.path.relpath(root, base_dir)
                        path_parts = rel_path.split(os.sep)
                        folder_diagram = ""
                        if len(path_parts) > 1:
                            # Use the last subfolder name as diagram (e.g., "4027F", "916H")
                            folder_diagram = path_parts[-1]

                        # Prefer folder name for diagram, fallback to JSON
                        diagram = folder_diagram if folder_diagram else route_data.get("diagram", "")

                        # Line code (e.g. "JO", "JK") = first 2 chars of any
                        # stop's sta_code. Used for the row-leading line badge.
                        line_code = ""
                        for stop in route_data.get("stops", []):
                            sc = stop.get("sta_code")
                            if sc and len(sc) >= 2:
                                line_code = sc[:2]
                                break

                        self.routes.append(
                            {
                                "path": root,
                                "name": route_data.get("route", "Unknown"),
                                "diagram": diagram,
                                "type": route_data.get("type", ""),
                                "dest": route_data.get("dest", ""),
                                "line_code": line_code,
                                "color": tuple(route_data.get("color") or (90, 90, 90)),
                            }
                        )
                except Exception as e:
                    print(f"Error loading {route_path}: {e}")

        # Sort by route name, then diagram, then type
        self.routes.sort(key=lambda r: (r["name"], r["diagram"], r["type"]))
        return self.routes

    def draw(self, selected_idx: int) -> None:
        """Draw the setup screen with route list.

        Args:
            selected_idx: Index of currently selected route
        """
        self.screen.fill(self.bg_color)

        # Draw title
        title = i18n.t("setup.title")
        title_img = self.title_font.render(title, True, self.text_color)
        title_x = (self.screen.get_width() - title_img.get_width()) // 2
        self.screen.blit(title_img, (title_x, 20))

        # "? Tutorial" button top-right (only after OOBE is complete).
        # Drawn before the route list so its hit-rect is set for the click loop.
        self._draw_tutorial_button()

        # Calculate visible area
        start_idx = 0
        end_idx = len(self.routes)

        if len(self.routes) > self.max_visible:
            # Adjust scroll to keep selection visible
            if selected_idx < self.scroll_offset:
                self.scroll_offset = selected_idx
            elif selected_idx >= self.scroll_offset + self.max_visible:
                self.scroll_offset = selected_idx - self.max_visible + 1
            start_idx = self.scroll_offset
            end_idx = min(self.scroll_offset + self.max_visible, len(self.routes))

        # Draw route list
        y_offset = 70
        for i in range(start_idx, end_idx):
            route = self.routes[i]
            display_idx = i - start_idx

            # Format route display text
            route_name = route["name"]
            diagram = route.get("diagram", "")
            route_type = route.get("type", "")
            dest = route.get("dest", "")

            # EN-mode lookup for type + dest from existing translation tables.
            # Route-name itself has no translation source; leaves as kanji. HK/CN
            # modes keep all data text as kanji per current scope.
            if i18n.current_lang() == "en":
                if route_type in self._train_types:
                    route_type = self._train_types[route_type].get("english", route_type)
                if dest in self._translations:
                    dest = self._translations[dest].get("english", dest).replace("\n", " ")

            # Line 2: Train type | Destination
            line2_parts = []
            if route_type:
                line2_parts.append(route_type)
            if dest:
                line2_parts.append(i18n.t("setup.dest_label", dest=dest))
            line2 = "  |  ".join(line2_parts) if line2_parts else ""

            # Selection highlight covers the full row.
            is_selected = i == selected_idx
            row_top = y_offset + display_idx * self.row_height
            if is_selected:
                highlight_rect = pygame.Rect(20, row_top, self.screen.get_width() - 40, self.row_height)
                pygame.draw.rect(self.screen, self.highlight_color, highlight_rect, border_radius=5)
                text_color = self.text_color
                line2_color = self.highlight_dim_color
            else:
                text_color = self.text_color
                line2_color = self.dim_color

            # Line badge at row's left edge (JR-style: 2-letter code, no station number).
            badge_right = self._draw_line_badge(
                x=30,
                cy=row_top + self.row_height // 2,
                line_code=route.get("line_code", ""),
                color=route.get("color", self.dim_color),
            )
            text_x = badge_right + 12

            # Pre-render both lines so we can vertically center the content block
            # inside the row. EN mode line 1 is two-pass (kanji name in CJK font +
            # Latin tail in Helvetica, baselines aligned via get_ascent() diff);
            # HK/CN modes are single-pass CJK throughout.
            if i18n.current_lang() == "en":
                line1_name_img = self.route_font_cjk.render(route_name, True, text_color)
                if diagram:
                    tail_text = f" - {i18n.t('setup.diagram_label', diagram=diagram)}"
                    line1_tail_img = self.route_font.render(tail_text, True, text_color)
                else:
                    line1_tail_img = None
                line1_h = line1_name_img.get_height()
            else:
                line1_name_img = None
                line1 = f"{route_name} - {i18n.t('setup.diagram_label', diagram=diagram)}" if diagram else route_name
                line1_tail_img = self.route_font.render(line1, True, text_color)
                line1_h = line1_tail_img.get_height()

            # In EN mode, dest/type may have stayed kanji if their entries are
            # missing from translations.json / train_types.json. HelveticaNeue
            # has no CJK glyphs → would render as tofu boxes. Detect any CJK
            # codepoint in line2 and fall back to the CJK font for that string.
            line2_font = self.route_font
            if line2 and i18n.current_lang() == "en" and any(0x3000 <= ord(c) <= 0x9FFF for c in line2):
                line2_font = self.route_font_cjk
            line2_img = line2_font.render(line2, True, line2_color) if line2 else None
            line2_h = line2_img.get_height() if line2_img else 0

            inter_gap = 2 if line2_img else 0
            content_h = line1_h + inter_gap + line2_h
            top_pad = max(0, (self.row_height - content_h) // 2)
            line1_y = row_top + top_pad
            line2_y = line1_y + line1_h + inter_gap

            # Blit line 1 (single- or two-pass)
            if line1_name_img is not None:
                self.screen.blit(line1_name_img, (text_x, line1_y))
                if line1_tail_img is not None:
                    ascent_diff = self.route_font_cjk.get_ascent() - self.route_font.get_ascent()
                    self.screen.blit(line1_tail_img, (text_x + line1_name_img.get_width(), line1_y + ascent_diff))
            else:
                self.screen.blit(line1_tail_img, (text_x, line1_y))

            # Line 2 — slightly indented from line 1 for visual hierarchy
            if line2_img is not None:
                self.screen.blit(line2_img, (text_x + 20, line2_y))

        # Draw scrollbar if there are more routes than visible
        if len(self.routes) > self.max_visible:
            self._draw_scrollbar()

        # Draw the OCR Auto-PA controls band (toggle pill + lead/interval steppers)
        self._draw_auto_pa_band()

        # Draw instructions (centered at bottom)
        instructions = i18n.t("setup.nav_hint")
        inst_img = self.instruction_font.render(instructions, True, self.dim_color)
        inst_x = (self.screen.get_width() - inst_img.get_width()) // 2
        self.screen.blit(inst_img, (inst_x, self.screen.get_height() - 35))

        pygame.display.flip()

    def _draw_auto_pa_band(self) -> None:
        """Render OCR Auto-PA toggle pill + lead/interval steppers, sized to fit
        between the route list and the bottom instruction row. All layout
        magic numbers live in the tuneable-params block at the top of the body.
        """
        # ── tuneable params ────────────────────────────────────────────────────
        band_y = self.screen.get_height() - 90  # band top
        band_h = 40
        side_pad = 20
        gap = 18  # gap between pill and steppers
        pill_w, pill_h = 170, 32
        step_btn = 26  # +/- button size (square)
        value_w = 56   # width reserved for "900m" / "5s" text
        # ────────────────────────────────────────────────────────────────────────

        cy = band_y + band_h // 2  # vertical center of band

        # Toggle pill (left side)
        pill_x = side_pad
        pill_y = cy - pill_h // 2
        self._toggle_rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)
        pill_bg = self.highlight_color if self.auto_input_enabled else self.control_bg
        pygame.draw.rect(self.screen, pill_bg, self._toggle_rect, border_radius=pill_h // 2)
        # Status dot
        dot_r = 6
        dot_cx = pill_x + 14
        dot_color = (255, 255, 255) if self.auto_input_enabled else (180, 180, 180)
        pygame.draw.circle(self.screen, dot_color, (dot_cx, cy), dot_r)
        # Label
        state = i18n.t("setup.on" if self.auto_input_enabled else "setup.off")
        label = i18n.t("setup.ocr_state", state=state)
        label_img = self.control_font.render(label, True, self.text_color)
        self.screen.blit(label_img, (dot_cx + dot_r + 6, cy - label_img.get_height() // 2))

        # Steppers — only fully active when toggle is ON; dim labels when OFF for
        # affordance, but clicks still work (lets user adjust before flipping ON).
        text_color = self.text_color if self.auto_input_enabled else self.dim_color
        btn_bg = self.control_bg if self.auto_input_enabled else self.control_dim

        def draw_stepper(label_text: str, value_text: str, x: int) -> tuple[int, pygame.Rect, pygame.Rect]:
            """Draw [Label: [-] value [+]] starting at x; return (right_edge, minus_rect, plus_rect)."""
            lbl = self.control_font.render(label_text, True, text_color)
            lbl_y = cy - lbl.get_height() // 2
            self.screen.blit(lbl, (x, lbl_y))
            cx = x + lbl.get_width() + 8
            minus = pygame.Rect(cx, cy - step_btn // 2, step_btn, step_btn)
            pygame.draw.rect(self.screen, btn_bg, minus, border_radius=4)
            minus_glyph = self.control_font.render("−", True, self.text_color)
            self.screen.blit(minus_glyph, (minus.centerx - minus_glyph.get_width() // 2, minus.centery - minus_glyph.get_height() // 2))
            cx = minus.right + 4
            val = self.control_font.render(value_text, True, text_color)
            self.screen.blit(val, (cx + (value_w - val.get_width()) // 2, cy - val.get_height() // 2))
            cx += value_w + 4
            plus = pygame.Rect(cx, cy - step_btn // 2, step_btn, step_btn)
            pygame.draw.rect(self.screen, btn_bg, plus, border_radius=4)
            plus_glyph = self.control_font.render("+", True, self.text_color)
            self.screen.blit(plus_glyph, (plus.centerx - plus_glyph.get_width() // 2, plus.centery - plus_glyph.get_height() // 2))
            return plus.right, minus, plus

        x = self._toggle_rect.right + gap
        x, self._lead_minus_rect, self._lead_plus_rect = draw_stepper(i18n.t("setup.lead_label"), f"{self.lead_m}m", x)
        x += gap
        _, self._interval_minus_rect, self._interval_plus_rect = draw_stepper(i18n.t("setup.interval_label"), f"{self.interval_s}s", x)

    def _handle_band_click(self, pos: tuple[int, int]) -> bool:
        """Dispatch a mouse click to the OCR Auto-PA band. Returns True if any
        control was hit (caller can stop propagation / suppress sound)."""
        if self._toggle_rect and self._toggle_rect.collidepoint(pos):
            self.auto_input_enabled = not self.auto_input_enabled
            return True
        if self._lead_minus_rect and self._lead_minus_rect.collidepoint(pos):
            self.lead_m = max(self.lead_min, self.lead_m - self.lead_step)
            return True
        if self._lead_plus_rect and self._lead_plus_rect.collidepoint(pos):
            self.lead_m = min(self.lead_max, self.lead_m + self.lead_step)
            return True
        if self._interval_minus_rect and self._interval_minus_rect.collidepoint(pos):
            self.interval_s = max(self.interval_min, self.interval_s - self.interval_step)
            return True
        if self._interval_plus_rect and self._interval_plus_rect.collidepoint(pos):
            self.interval_s = min(self.interval_max, self.interval_s + self.interval_step)
            return True
        return False

    def _draw_tutorial_button(self) -> None:
        """Render the "? Tutorial" replay button top-right. Sets
        ``_tutorial_btn_rect`` for the click handler. No-op when
        ``show_tutorial_button`` is False (first-launch users haven't seen
        the tutorial yet, so we don't surface a "replay" affordance)."""
        if not self.show_tutorial_button:
            self._tutorial_btn_rect = None
            return
        # ── tuneable params ──────────────────────────────────────
        margin_right = 12
        margin_top = 12
        btn_h = 28
        btn_pad_x = 12
        # ─────────────────────────────────────────────────────────
        label = i18n.t("setup.tutorial_button")
        label_img = self.control_font.render(label, True, self.text_color)
        btn_w = label_img.get_width() + 2 * btn_pad_x
        btn_x = self.screen.get_width() - margin_right - btn_w
        btn_y = margin_top
        rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        pygame.draw.rect(self.screen, self.control_bg, rect, border_radius=btn_h // 2)
        self.screen.blit(
            label_img,
            (rect.centerx - label_img.get_width() // 2,
             rect.centery - label_img.get_height() // 2),
        )
        self._tutorial_btn_rect = rect

    def _draw_line_badge(self, x: int, cy: int, line_code: str, color: tuple) -> int:
        """Draw a JR-style line marker (2-letter code only, no station number) via
        the LCD's canonical badge helper. Vertically centered at `cy`. Returns the
        right-edge x for placing subsequent content — when line_code is empty
        (route has no sta_code), no badge is drawn and `x` is returned unchanged
        so text isn't pushed right by a phantom badge width."""
        # ── tuneable params ────────────────
        badge_w, badge_h = 38, 38
        # ────────────────────────────────────
        if not line_code:
            return x
        draw_station_code_badge(
            self.screen,
            x=x,
            y=cy - badge_h // 2,
            w=badge_w,
            h=badge_h,
            sta_code=line_code,
            color=color,
            font_prefix=self.badge_font,
            font_num=self.badge_font,  # unused in line-marker mode
            ring_black=2,
            ring_color=3,
            outer_radius=5,
            color_radius=3,
            interior_radius=0,
        )
        return x + badge_w

    def _draw_scrollbar(self) -> None:
        """Draw a scrollbar indicator on the right side."""
        if len(self.routes) <= self.max_visible:
            return

        # Calculate scrollbar dimensions
        bar_x = self.screen.get_width() - 8
        bar_width = 6
        list_area_start = 70
        list_area_height = self.max_visible * self.row_height

        # Calculate thumb position and height
        thumb_height = max(30, (self.max_visible / len(self.routes)) * list_area_height)
        scroll_ratio = self.scroll_offset / (len(self.routes) - self.max_visible)
        thumb_y = int(list_area_start + scroll_ratio * (list_area_height - thumb_height))

        # Draw scrollbar track
        pygame.draw.rect(self.screen, (80, 80, 80), pygame.Rect(bar_x, list_area_start, bar_width, list_area_height), border_radius=3)

        # Draw scrollbar thumb
        pygame.draw.rect(self.screen, (180, 180, 180), pygame.Rect(bar_x, thumb_y, bar_width, int(thumb_height)), border_radius=3)

    def run(self) -> dict | None:
        """Run the setup screen loop. Returns an action-keyed dict or None.

        Returns:
            ``{"action": "select", **config}`` when a route is confirmed
                (config keys: ``work_dir``, ``route_data``, ``auto_input``,
                ``lead_m``, ``interval_s``).
            ``{"action": "run_tutorial"}`` when the user clicks the
                "? Tutorial" button (only shown when ``show_tutorial_button``
                is True). Caller is expected to run the tutorial then call
                ``run()`` again to re-show the route picker.
            ``None`` if the user cancels (ESC / window close).
        """
        self.scan_routes()

        if not self.routes:
            print(i18n.t("setup.no_routes"))
            return None

        # Store original key repeat state to restore later
        # pygame.key.get_repeat() returns (delay, interval) or None if repeat is disabled
        original_repeat = pygame.key.get_repeat()

        # Enable key repeat for arrow keys using configured timing
        # This allows holding down arrow keys to scroll continuously
        pygame.key.set_repeat(SETUP_KEY_REPEAT_DELAY, SETUP_KEY_REPEAT_INTERVAL)

        running = True

        try:
            while running:
                self.draw(self.selected_idx)

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return None
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # ? Tutorial button takes priority — sits above the
                        # OCR auto-PA band, so check it first.
                        if (
                            self._tutorial_btn_rect is not None
                            and self._tutorial_btn_rect.collidepoint(event.pos)
                        ):
                            return {"action": "run_tutorial"}
                        self._handle_band_click(event.pos)
                        continue
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            return None
                        elif event.key == pygame.K_UP:
                            self.selected_idx = max(0, self.selected_idx - 1)
                        elif event.key == pygame.K_DOWN:
                            self.selected_idx = min(len(self.routes) - 1, self.selected_idx + 1)
                        elif event.key == pygame.K_RETURN:
                            if self.routes:
                                selected = self.routes[self.selected_idx]
                                # Load full route data
                                try:
                                    with open(os.path.join(selected["path"], "route.json"), encoding="utf-8") as f:
                                        route_data = json.load(f)
                                    return {
                                        "action": "select",
                                        "work_dir": selected["path"],
                                        "route_data": route_data,
                                        "auto_input": self.auto_input_enabled,
                                        "lead_m": self.lead_m,
                                        "interval_s": self.interval_s,
                                    }
                                except Exception as e:
                                    print(f"Error loading route data: {e}")
                                    return None
        finally:
            # Restore original key repeat state when exiting setup screen
            # This ensures the main simulator doesn't inherit modified key repeat settings
            if original_repeat is None:
                pygame.key.set_repeat()  # Disable repeat
            else:
                # Restore exact original delay and interval values
                delay, interval = original_repeat
                pygame.key.set_repeat(delay, interval)
        return None

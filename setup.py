"""Setup screen for route and train selection."""

import math
import os
import json
import random
import webbrowser
import pygame

import i18n
import update_check
from app_paths import project_root, load_json_relative
from constants import SETUP_KEY_REPEAT_DELAY, SETUP_KEY_REPEAT_INTERVAL


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

        The OCR Auto-PA band (toggle pill + lead/interval steppers) always
        renders; it stays opt-in via the pill's consent disclaimer.
        """
        self.screen = screen
        self.show_tutorial_button = show_tutorial_button
        self.routes = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.row_height = 50
        self._tutorial_btn_rect: pygame.Rect | None = None
        # Update-available hint (top-left) — populated by _draw_update_hint when
        # update_check found a newer release; read by run() for the click.
        self._update_hint_rect: pygame.Rect | None = None
        self._update_url: str | None = None
        # Reserve ~60px below the route list for the OCR Auto-PA band, plus the usual
        # title (50px) and instructions (50px). Route list shrinks from 6 to 5 visible
        # rows on the default 420px-tall window.
        available_height = screen.get_height() - 160
        self.max_visible = max(3, available_height // self.row_height)

        # Chrome fonts via i18n.font() — bundled OTFs per language: HelveticaNeue
        # (en, PIDS-canon Latin), ShinGoPr6N (zh_HK), Noto Sans CJK SC (zh_CN).
        # `route_font_cjk` is pinned to a CJK language explicitly because route
        # names on line 1 are Japanese kanji today (translation deferred); used
        # for the kanji portion of line 1 in EN mode (two-pass with tail Latin).
        self.title_font = i18n.font(28, bold=True)
        self.route_font = i18n.font(18, bold=True)
        self.instruction_font = i18n.font(16, bold=True)
        self.control_font = i18n.font(14, bold=True)
        self.route_font_cjk = i18n.font_for_lang("zh_HK", 18, bold=True)
        # Line badge icons — authentic Wikipedia SVG-sourced PNGs from
        # data/line_icons/, same assets the transfer-info display uses.
        self._line_icon_cache: dict[str, pygame.Surface] = {}
        self._line_icon_h = 38  # target height; width scales proportionally

        # Translation tables for EN mode lookup of route-level data fields.
        # zh_HK / zh_CN modes keep route-data text in kanji (no source data exists
        # today); only the chrome strings around it translate.
        self._translations = load_json_relative("data/translations.json")
        self._train_types = load_json_relative("data/train_types.json")

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

        # OCR Auto-PA controls — persisted in settings.json under "auto_input".
        # Lead/interval clamped to the ranges below.
        self.auto_input_enabled = bool(i18n.load_settings().get("auto_input", False))
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
        self._last_mouse_pos = (0, 0)

        # Cached raw screenshot surface for the OCR disclaimer popup.
        # Loaded once on first draw; False = tried and failed (no file / load error).
        self._disclaimer_screenshot: pygame.Surface | bool | None = None
        # Pre-cropped HUD panel image (hud_sample.png) for box 2.
        self._disclaimer_hud: pygame.Surface | bool | None = None
        # Cached OCR template surfaces for the pipeline visual strip (lazy-loaded).
        # List of (surface, label) pairs; empty list = already attempted (no templates found).
        self._disclaimer_templates: list[tuple[pygame.Surface, str]] | None = None
        # Suica-penguin train icon for the trigger-timing diagram (lazy-loaded).
        self._disclaimer_train: pygame.Surface | bool | None = None

    def scan_routes(self, base_dir: str | None = None) -> list:
        """Scan for available routes by finding route.json files.

        Groups routes by name, then by train diagram.
        Extracts diagram from folder name when available (e.g., nambu/4027F/route.json).

        Args:
            base_dir: Base directory to scan for routes (defaults to "audio" under project root)

        Returns:
            List of route dictionaries
        """
        self.routes = []
        if base_dir is None:
            base_dir = str(project_root() / "audio")

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

        # "Update available" hint top-left (only when a newer release was found).
        self._draw_update_hint()

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
        value_w = 56  # width reserved for "900m" / "5s" text
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

    def _draw_ocr_disclaimer_panel(self, screen: pygame.Surface, scroll_y: int = 0) -> tuple[pygame.Rect, pygame.Rect, int]:
        """Draw the scrollable OCR disclaimer/consent panel.

        Returns (ok_rect, cancel_rect, max_scroll).
        ok_rect is grayed when scroll_y < max_scroll — caller enforces the lock."""
        # ── tuneable params ────────────────────────────────────────────────
        sw, sh = screen.get_width(), screen.get_height()
        pad = 24
        diag_h = 230  # max screenshot height
        btn_h = 36
        btn_w = 150
        btn_gap = 10
        header_h = 54  # title + divider
        footer_h = 64  # buttons row
        clip_top = header_h
        clip_h = sh - header_h - footer_h
        # ───────────────────────────────────────────────────────────────────

        panel_color = (52, 57, 72)
        border_color = (90, 98, 118)
        heading_color = (200, 210, 230)

        pygame.draw.rect(screen, panel_color, pygame.Rect(0, 0, sw, sh), border_radius=10)
        pygame.draw.rect(screen, border_color, pygame.Rect(0, 0, sw, sh), width=1, border_radius=10)

        # ── Fixed header ───────────────────────────────────────────────────
        title_font = i18n.font(16, bold=True)
        title_img = title_font.render(i18n.t("setup.ocr_disclaimer.title"), True, self.text_color)
        screen.blit(title_img, (pad, (header_h - title_img.get_height()) // 2))
        pygame.draw.line(screen, border_color, (pad, header_h - 1), (sw - pad, header_h - 1))

        # ── Scrollable content ─────────────────────────────────────────────
        screen.set_clip(pygame.Rect(0, clip_top, sw - 12, clip_h))

        body_font = i18n.font(13)
        subhead_font = i18n.font(13, bold=True)
        cap_font = i18n.font(11)

        # Lazy-load screenshot (once per SetupScreen instance)
        if self._disclaimer_screenshot is None:
            try:
                _p = project_root() / "data" / "disclaimer" / "game_screenshot.png"
                self._disclaimer_screenshot = pygame.image.load(str(_p)).convert() if _p.exists() else False
            except Exception:
                self._disclaimer_screenshot = False
        if self._disclaimer_hud is None:
            try:
                _p = project_root() / "data" / "disclaimer" / "hud_sample.png"
                self._disclaimer_hud = pygame.image.load(str(_p)).convert() if _p.exists() else False
            except Exception:
                self._disclaimer_hud = False

        # Draw cursor starts at virtual top offset by scroll
        y = clip_top + 16 - scroll_y

        # ── 功能說明 section heading ───────────────────────────────────────
        hw_img = subhead_font.render(i18n.t("setup.ocr_disclaimer.how_it_works_heading"), True, heading_color)
        screen.blit(hw_img, (pad, y))
        y += hw_img.get_height() + 10

        # ── Two-column top: intro text (left) + screenshot (right) ────────
        left_col_w = 210
        col_gap = 16
        right_col_x = pad + left_col_w + col_gap
        right_col_w = sw - pad - right_col_x
        row_top = y

        # Left: intro text — pixel-width word wrap (CJK char-by-char, Latin word-boundary)
        def wrap_text(font, text, max_w):
            """Pixel-width wrap. CJK: cut at column edge. Latin: backtrack to word boundary.
            Mixed Latin+CJK: don't backtrack across a Latin→CJK boundary."""
            lines, current = [], ""
            for ch in text:
                test = current + ch
                if font.size(test)[0] <= max_w:
                    current = test
                    continue
                if not current:
                    lines.append(ch)
                    continue
                if ch == " ":
                    lines.append(current)
                    current = ""
                else:
                    sp = current.rfind(" ")
                    after = current[sp + 1 :] if sp >= 0 else ""
                    # Backtrack to space only when continuation stays Latin
                    if sp > 0 and after and ord(after[0]) < 0x3000:
                        lines.append(current[:sp])
                        current = after + ch
                    else:
                        lines.append(current)
                        current = ch
            if current:
                lines.append(current)
            return lines

        intro_y = row_top
        for para in i18n.t("setup.ocr_disclaimer.intro").split("\n"):
            if not para:
                intro_y += body_font.get_height() // 2
                continue
            for line in wrap_text(body_font, para, left_col_w):
                img = body_font.render(line, True, self.text_color)
                screen.blit(img, (pad, intro_y))
                intro_y += img.get_height() + 2

        # Resolution note: right below intro paragraph, same font + column width.
        # (The misfire caveat moved to the "When Auto-PA fires" section below.)
        intro_y += 8
        for line in wrap_text(body_font, i18n.t("setup.ocr_disclaimer.resolution"), left_col_w):
            img = body_font.render(line, True, (230, 180, 60))
            screen.blit(img, (pad, intro_y))
            intro_y += img.get_height() + 2

        # Right: screenshot + HUD pulse
        if self._disclaimer_screenshot is not False:
            raw = self._disclaimer_screenshot
            rw, rh = raw.get_size()
            scale = min(right_col_w / rw, diag_h / rh)
            ss = pygame.transform.smoothscale(raw, (int(rw * scale), int(rh * scale)))
            img_x = right_col_x + (right_col_w - ss.get_width()) // 2
            screen.blit(ss, (img_x, row_top))
            pygame.draw.rect(screen, (70, 78, 96), pygame.Rect(img_x, row_top, ss.get_width(), ss.get_height()), width=1)
            sc_w, sc_h = ss.get_size()
            hud_abs_x = img_x + int(sc_w * 0.78)
            hud_abs_w = sc_w - int(sc_w * 0.78)
            hud_abs_h = int(sc_h * 0.48)
            phase = (pygame.time.get_ticks() % 1500) / 1500
            brightness = math.sin(phase * math.pi)
            hud_alpha = int(brightness * 210)
            hud_surf = pygame.Surface((hud_abs_w, hud_abs_h), pygame.SRCALPHA)
            hud_surf.fill((255, 200, 60, hud_alpha))
            pygame.draw.rect(hud_surf, (255, 210, 80, min(255, hud_alpha + 50)), pygame.Rect(0, 0, hud_abs_w, hud_abs_h), width=2)
            screen.blit(hud_surf, (hud_abs_x, row_top))
            row_h = ss.get_height()
        else:
            # Fallback hand-drawn diagram in right column
            fb = pygame.Rect(right_col_x, row_top, right_col_w, diag_h)
            pygame.draw.rect(screen, (22, 26, 38), fb, border_radius=4)
            pygame.draw.rect(screen, (70, 78, 96), fb, width=1, border_radius=4)
            hud_x_fb = fb.right - 4 - 46
            hud_surf_fb = pygame.Surface((46, 26), pygame.SRCALPHA)
            hud_surf_fb.fill((255, 200, 60, 55))
            screen.blit(hud_surf_fb, (hud_x_fb, fb.top + 4))
            pygame.draw.rect(screen, (255, 200, 60), pygame.Rect(hud_x_fb, fb.top + 4, 46, 26), width=1, border_radius=2)
            row_h = diag_h

        y = row_top + max(intro_y - row_top, row_h) + 6
        cap_img = cap_font.render(i18n.t("setup.ocr_disclaimer.capture_interval", n=self.interval_s), True, self.dim_color)
        screen.blit(cap_img, (right_col_x + (right_col_w - cap_img.get_width()) // 2, y))
        y += cap_img.get_height() + 16

        # ── Working Principle: 4-step pipeline flowchart ──────────────────
        wp_head = subhead_font.render(i18n.t("setup.ocr_disclaimer.mechanism_heading"), True, heading_color)
        screen.blit(wp_head, (pad, y))
        y += wp_head.get_height() + 10

        # ── 4-step pipeline flowchart ──────────────────────────────────────
        chart_w = sw - 2 * pad
        arrow_w = 18
        step_w = (chart_w - 3 * arrow_w) // 4
        flow_h = 68
        inner = 5

        flow_labels = [
            i18n.t("setup.ocr_disclaimer.flow.capture"),
            i18n.t("setup.ocr_disclaimer.flow.match"),
            i18n.t("setup.ocr_disclaimer.flow.deduce"),
            i18n.t("setup.ocr_disclaimer.flow.fire"),
        ]

        # Lazy-load templates for step 1 box
        if self._disclaimer_templates is None:
            self._disclaimer_templates = []
            tpl_root = project_root() / "ocr_templates"
            for bn in ["stopping_ja", "running_ja", "passing_en"]:
                p = tpl_root / "badges" / f"{bn}.png"
                if p.exists():
                    try:
                        self._disclaimer_templates.append((pygame.image.load(str(p)).convert_alpha(), ""))
                    except Exception:
                        pass
            for d in ["0", "1", "2", "8", "9"]:
                p = tpl_root / "digits" / f"{d}.png"
                if p.exists():
                    try:
                        self._disclaimer_templates.append((pygame.image.load(str(p)).convert_alpha(), d))
                    except Exception:
                        pass

        for i in range(4):
            sx = pad + i * (step_w + arrow_w)
            box = pygame.Rect(sx, y, step_w, flow_h)
            pygame.draw.rect(screen, (62, 68, 82), box, border_radius=5)
            pygame.draw.rect(screen, border_color, box, width=1, border_radius=5)
            cw, ch = step_w - 2 * inner, flow_h - 2 * inner

            if i == 0 and self._disclaimer_screenshot is not False:
                raw = self._disclaimer_screenshot
                rw, rh = raw.get_size()
                hud_rect = pygame.Rect(int(rw * 0.78), 0, rw - int(rw * 0.78), int(rh * 0.48))
                hud = raw.subsurface(hud_rect)
                hw, hh = hud.get_size()
                sc = min(cw / hw, ch / hh)
                scaled = pygame.transform.smoothscale(hud, (int(hw * sc), int(hh * sc)))
                screen.blit(scaled, (sx + inner + (cw - scaled.get_width()) // 2, y + inner + (ch - scaled.get_height()) // 2))

            elif i == 1 and self._disclaimer_templates:
                # Left: real distance-cell crop from bundled screenshot.
                # Right: digit templates cycle to show the scanning process.
                dist_img = None
                if self._disclaimer_hud is not False:
                    ow_d, oh_d = self._disclaimer_hud.get_size()
                    ds = min((cw * 0.55) / ow_d, (ch - 8) / oh_d)
                    dist_img = pygame.transform.smoothscale(self._disclaimer_hud, (max(1, int(ow_d * ds)), max(1, int(oh_d * ds))))

                vx = sx + inner + 4
                if dist_img is not None:
                    vy = y + inner + (ch - dist_img.get_height()) // 2
                    screen.blit(dist_img, (vx, vy))
                    vw_used = dist_img.get_width()
                    target_th = dist_img.get_height()
                else:
                    vw_used = 0
                    target_th = ch - 8

                digit_entries = [(s, lbl) for s, lbl in self._disclaimer_templates if lbl.isdigit()]
                if digit_entries:
                    tpl_idx = (pygame.time.get_ticks() // 350) % len(digit_entries)
                    tpl_surf, tpl_lbl = digit_entries[tpl_idx]
                    # "855" = digits visible in bundled screenshot's distance cell
                    is_match = tpl_lbl in "855"

                    ow, oh = tpl_surf.get_size()
                    tw = max(1, int(ow * target_th / oh))
                    scaled_d = pygame.transform.scale(tpl_surf, (tw, target_th))

                    rx_start = vx + vw_used + 10
                    remaining = (sx + step_w - inner) - rx_start
                    tx = rx_start + max(0, (remaining - tw) // 2)
                    ty = y + inner + (ch - target_th) // 2

                    if is_match:
                        pygame.draw.rect(screen, (230, 180, 60), pygame.Rect(tx - 3, ty - 3, tw + 6, target_th + 6), width=2, border_radius=3)
                    screen.blit(scaled_d, (tx, ty))

            elif i == 2:
                # "v × t → d" — larger font to fill the box like the other steps;
                # the → is drawn as a vector arrow (the chrome font is Latin-only
                # and tofus U+2192; × is Latin-1 and renders fine).
                f3 = i18n.font(20, bold=True)
                left = f3.render("v × t", True, self.text_color)
                right = f3.render("d", True, self.text_color)
                arr_gap = 24
                total = left.get_width() + arr_gap + right.get_width()
                lx = box.centerx - total // 2
                cy = box.centery
                screen.blit(left, (lx, cy - left.get_height() // 2))
                ax0 = lx + left.get_width() + 5
                ax1 = lx + left.get_width() + arr_gap - 4
                pygame.draw.line(screen, self.text_color, (ax0, cy), (ax1 - 2, cy), 3)
                pygame.draw.polygon(screen, self.text_color, [(ax1 - 5, cy - 5), (ax1 + 1, cy), (ax1 - 5, cy + 5)])
                screen.blit(right, (lx + left.get_width() + arr_gap, cy - right.get_height() // 2))

            elif i == 3:
                # Animated PgDn key: cap slides down over shadow face on press
                key_w, cap_h = 56, 28
                shadow_h = 5  # fixed dark bottom face
                t_norm = (pygame.time.get_ticks() % 2000) / 2000
                if t_norm < 0.10:
                    press = t_norm / 0.10
                elif t_norm < 0.50:
                    press = 1.0
                elif t_norm < 0.65:
                    press = 1.0 - (t_norm - 0.50) / 0.15
                else:
                    press = 0.0
                press_off = int(press * shadow_h)
                kx = box.centerx - key_w // 2
                ky = box.centery - (cap_h + shadow_h) // 2

                # Shadow face (stays fixed — cap slides over it when pressed)
                pygame.draw.rect(screen, (32, 36, 48), pygame.Rect(kx, ky + cap_h, key_w, shadow_h), border_radius=4)
                # Cap (moves down)
                cap_y = ky + press_off
                pygame.draw.rect(screen, (75, 82, 100), pygame.Rect(kx, cap_y, key_w, cap_h), border_radius=5)
                # Highlight strip on top of cap for 3D bevel
                pygame.draw.rect(screen, (95, 103, 124), pygame.Rect(kx + 2, cap_y + 2, key_w - 4, 3), border_radius=2)
                pygame.draw.rect(screen, border_color, pygame.Rect(kx, cap_y, key_w, cap_h), width=1, border_radius=5)
                klbl = subhead_font.render("PgDn", True, self.text_color)
                screen.blit(klbl, (kx + (key_w - klbl.get_width()) // 2, cap_y + (cap_h - klbl.get_height()) // 2))

            # Label below box
            lbl = cap_font.render(flow_labels[i], True, self.dim_color)
            screen.blit(lbl, (box.centerx - lbl.get_width() // 2, y + flow_h + 4))

            # Connector arrow between boxes — drawn as a vector shaft + head (the
            # chrome font tofus the → glyph in en; a primitive is deployment-safe).
            if i < 3:
                cy = y + flow_h // 2
                ax = sx + step_w + 3
                ahead = sx + step_w + arrow_w - 3
                pygame.draw.line(screen, self.dim_color, (ax, cy), (ahead - 2, cy), 2)
                pygame.draw.polygon(screen, self.dim_color, [(ahead - 4, cy - 3), (ahead, cy), (ahead - 4, cy + 3)])

        y += flow_h + 4 + cap_font.get_height() + 16

        # ── Trigger timings: journey diagram ──────────────────────────────
        jhead = subhead_font.render(i18n.t("setup.ocr_disclaimer.journey_heading"), True, heading_color)
        screen.blit(jhead, (pad, y))
        y += jhead.get_height() + 10

        # Geometry — stations sit inboard (room for detail); markers pulled centreward
        j_x0 = pad + 44
        j_x1 = sw - pad - 44
        jw = j_x1 - j_x0
        track_y = y + 84  # rail line = horizon; backdrop rises above it
        rail_gap = 6

        dep_frac, appr_frac = 0.30, 0.70
        dep_x = int(j_x0 + jw * dep_frac)
        appr_x = int(j_x0 + jw * appr_frac)
        arr_x = j_x1

        _RAIL_HI = (238, 242, 250)  # bright rail-head highlight
        _RAIL = (196, 202, 214)  # rail body (bright steel)
        _RAIL_DK = (128, 134, 148)  # rail foot / web shadow
        _SLP = (150, 112, 78)  # warm wooden sleeper (tie) — daytime
        _SLP_HI = (176, 136, 96)  # sunlit top of the tie
        _BALLAST = (120, 120, 126)  # gravel bed — light gray, contrasts
        _DEP = (82, 196, 118)
        _APPR = (230, 178, 58)
        _ARR = (98, 164, 228)
        rail_top = track_y
        rail_bot = track_y
        horizon = track_y

        def _ipts(pts):
            return [(int(px), int(py)) for px, py in pts]

        # ── Backdrop, far → near (flat daytime sticker silhouettes, bright on dark bg) ──
        # Mt. Fuji — broad snow-capped cone, clear-day blue, farthest back
        def draw_fuji(cx, base, h=40, hw=72):
            pygame.draw.polygon(
                screen,
                (124, 148, 196),
                _ipts(
                    [
                        (cx - hw, base),
                        (cx - hw * 0.2, base - h * 0.9),
                        (cx - 7, base - h),
                        (cx + 7, base - h),
                        (cx + hw * 0.2, base - h * 0.9),
                        (cx + hw, base),
                    ]
                ),
            )
            pygame.draw.polygon(
                screen,
                (240, 244, 252),
                _ipts(
                    [
                        (cx - 7, base - h),
                        (cx + 7, base - h),
                        (cx + 13, base - h * 0.74),
                        (cx + 6, base - h * 0.78),
                        (cx + 1, base - h * 0.73),
                        (cx - 4, base - h * 0.79),
                        (cx - 9, base - h * 0.74),
                        (cx - 13, base - h * 0.74),
                    ]
                ),
            )

        # Daytime skyline — bright colorful building blocks + subtle glass windows
        _BLD_TONES = [(150, 162, 188), (188, 158, 168), (146, 188, 190), (192, 180, 150), (164, 172, 200), (200, 168, 150)]

        def draw_skyline(x0, x1, seed):
            rng = random.Random(seed)  # deterministic per span (no flicker)
            bx = x0
            while bx < x1:
                bw = rng.randint(8, 16)
                bh = rng.randint(10, 24)
                top = horizon - bh
                tone = rng.choice(_BLD_TONES)
                pygame.draw.rect(screen, tone, pygame.Rect(bx, top, bw, bh))
                # Sunlit left edge + recessed glass windows for daytime depth
                pygame.draw.rect(screen, tuple(min(255, c + 26) for c in tone), pygame.Rect(bx, top, 2, bh))
                glass = tuple(max(0, c - 48) for c in tone)
                for wy in range(top + 3, horizon - 2, 5):
                    for wx in range(bx + 3, bx + bw - 2, 4):
                        pygame.draw.rect(screen, glass, pygame.Rect(wx, wy, 1, 2))
                bx += bw + rng.randint(1, 4)

        # Tokyo Skytree — tall tapering lattice needle, bright daytime white-blue
        def draw_skytree(cx, base, h=52):
            col = (196, 214, 234)
            pygame.draw.polygon(
                screen,
                col,
                _ipts(
                    [
                        (cx - 4, base),
                        (cx - 1.5, base - h * 0.5),
                        (cx - 1.2, base - h * 0.84),
                        (cx + 1.2, base - h * 0.84),
                        (cx + 1.5, base - h * 0.5),
                        (cx + 4, base),
                    ]
                ),
            )
            pygame.draw.ellipse(screen, col, pygame.Rect(int(cx - 5), int(base - h * 0.60), 10, 5))
            pygame.draw.ellipse(screen, col, pygame.Rect(int(cx - 3), int(base - h * 0.74), 6, 4))
            pygame.draw.line(screen, col, (cx, int(base - h * 0.84)), (cx, int(base - h)), 1)

        # Tokyo Tower — international-orange + white bands, lattice bracing, two decks
        def draw_tower(cx, base, h=46):
            col, white, dk, ant = (228, 118, 80), (244, 234, 224), (180, 86, 58), (210, 212, 218)
            yb = lambda f: int(base - h * f)
            # Splayed lattice base (orange) with X cross-bracing + horizontal struts
            pygame.draw.polygon(screen, col, _ipts([(cx - 11, base), (cx - 4, base - h * 0.34), (cx + 4, base - h * 0.34), (cx + 11, base)]))
            pygame.draw.line(screen, dk, (cx - 11, base), (cx + 4, yb(0.34)), 1)
            pygame.draw.line(screen, dk, (cx + 11, base), (cx - 4, yb(0.34)), 1)
            pygame.draw.line(screen, white, (cx - 8, yb(0.12)), (cx + 8, yb(0.12)), 1)
            pygame.draw.line(screen, white, (cx - 5, yb(0.25)), (cx + 5, yb(0.25)), 1)
            # Main observation deck (大展望台) — wider, white-banded, lit windows
            pygame.draw.rect(screen, col, pygame.Rect(int(cx - 7), yb(0.45), 14, 4))
            pygame.draw.rect(screen, white, pygame.Rect(int(cx - 7), yb(0.45), 14, 1))
            for wx in range(int(cx - 5), int(cx + 5), 3):
                pygame.draw.rect(screen, dk, pygame.Rect(wx, yb(0.45) + 2, 1, 2))
            # Upper shaft (orange) with white bands + central lattice line
            pygame.draw.polygon(
                screen, col, _ipts([(cx - 4, base - h * 0.45), (cx - 2, base - h * 0.72), (cx + 2, base - h * 0.72), (cx + 4, base - h * 0.45)])
            )
            pygame.draw.line(screen, dk, (cx, yb(0.45)), (cx, yb(0.72)), 1)
            pygame.draw.line(screen, white, (cx - 3, yb(0.56)), (cx + 3, yb(0.56)), 1)
            # Special deck (特別展望台) + antenna spire
            pygame.draw.rect(screen, col, pygame.Rect(int(cx - 3), yb(0.74), 6, 2))
            pygame.draw.rect(screen, white, pygame.Rect(int(cx - 3), yb(0.74), 6, 1))
            pygame.draw.line(screen, ant, (cx, yb(0.76)), (cx, base - h), 1)

        # Station A — Tokyo Station Marunouchi: tripartite red-brick facade with
        # projecting/recessed depth shading, white stone string-courses + quoins,
        # blue slate mansard roof w/ dormers, twin plum SPIRED octagonal turrets
        # (not domes), central gabled clock pavilion + cupola.
        def draw_station_classic(sx):
            # Depth via projecting vs recessed masses under upper-left light: the
            # end towers + central pavilion sit forward (lit brick), the connecting
            # wings sit back (dark brick), with cast-shadow strips at each step.
            brick, brick_dk, brick_sh = (182, 96, 80), (150, 74, 62), (130, 62, 52)
            brick_hi, band, band_sh = (202, 112, 94), (240, 236, 226), (206, 200, 188)
            slate, slate_hi, slate_dk = (84, 106, 138), (132, 156, 188), (52, 70, 98)
            clockc, arch, glassw, finial = (38, 42, 52), (44, 36, 36), (150, 172, 196), (238, 234, 224)
            bw, bh = 80, 26
            body = pygame.Rect(sx - bw // 2, horizon - bh, bw, bh)

            # Recessed wings (set-back wall) fill the whole body; forward masses
            # repaint over it brighter.
            pygame.draw.rect(screen, brick_dk, body)
            lt = pygame.Rect(body.x, body.y, 16, bh)  # left tower column (forward)
            rt = pygame.Rect(body.right - 16, body.y, 16, bh)  # right tower column
            cp = pygame.Rect(sx - 12, body.y, 24, bh)  # central pavilion column
            for col in (lt, cp, rt):
                pygame.draw.rect(screen, brick, col)
                pygame.draw.line(screen, brick_hi, (col.x, col.y), (col.x, horizon - 1), 1)  # lit left edge
            # Cast shadows: each forward mass darkens the recessed wing to its right
            pygame.draw.rect(screen, brick_sh, pygame.Rect(lt.right, body.y, 2, bh))
            pygame.draw.rect(screen, brick_sh, pygame.Rect(cp.right, body.y, 2, bh))

            # White stone string-courses across the facade; shadow-tinted over wings
            for by in range(body.y + 5, horizon - 2, 5):
                pygame.draw.rect(screen, band_sh, pygame.Rect(body.x, by, bw, 2))
                for col in (lt, cp, rt):
                    pygame.draw.rect(screen, band, pygame.Rect(col.x, by, col.width, 2))
            # Window rows between the bands
            for ry in range(body.y + 6, horizon - 8, 5):
                for wx in range(body.x + 7, body.right - 6, 7):
                    pygame.draw.rect(screen, glassw, pygame.Rect(wx, ry, 2, 3))
            # Arched ground-floor openings (dark), capped by a pale stone sill
            pygame.draw.rect(screen, band_sh, pygame.Rect(body.x, horizon - 7, bw, 1))
            for ax in range(body.x + 6, body.right - 6, 9):
                pygame.draw.rect(screen, arch, pygame.Rect(ax, horizon - 6, 5, 6), border_top_left_radius=2, border_top_right_radius=2)

            # Blue slate mansard roof: front band + a darker receding top plane + dormers
            roof = pygame.Rect(body.x + 10, body.y - 4, bw - 20, 4)
            pygame.draw.polygon(  # top plane recedes (narrower at back) = depth
                screen, slate_dk, _ipts([(roof.x, roof.y), (roof.right, roof.y), (roof.right - 4, roof.y - 3), (roof.x + 4, roof.y - 3)])
            )
            pygame.draw.rect(screen, slate, roof)
            pygame.draw.line(screen, slate_hi, (roof.x, roof.y), (roof.right, roof.y), 1)
            for dxm in range(roof.x + 5, roof.right - 4, 9):
                pygame.draw.rect(screen, slate, pygame.Rect(dxm, roof.y - 2, 3, 2))
                pygame.draw.rect(screen, glassw, pygame.Rect(dxm, roof.y - 1, 3, 1))
            # White corner quoins (cap the facade edges, run up past the roof band)
            pygame.draw.rect(screen, band, pygame.Rect(body.x, body.y - 4, 3, bh + 4))
            pygame.draw.rect(screen, band_sh, pygame.Rect(body.right - 3, body.y - 4, 3, bh + 4))

            # Twin octagonal SPIRED turrets (the corner pavilions — tiered pointed
            # hip roof → small cap → tall needle spire + finial ball, NOT domes),
            # dark plum slate so they read distinct from the blue central/mansard roofs.
            plum, plum_hi, plum_dk = (120, 86, 106), (152, 118, 138), (84, 58, 76)

            def _turret(dcx):
                base_y = horizon - bh - 6  # pavilion top = roof springing line
                pygame.draw.rect(screen, brick, pygame.Rect(dcx - 8, base_y, 16, 6))
                pygame.draw.line(screen, brick_hi, (dcx - 8, base_y), (dcx - 8, base_y + 6), 1)
                pygame.draw.rect(screen, band, pygame.Rect(dcx - 8, base_y, 16, 1))
                pygame.draw.rect(screen, plum_dk, pygame.Rect(dcx - 9, base_y - 1, 18, 1))  # eave overhang
                # tier 1 — wide flared hip roof
                pygame.draw.polygon(screen, plum, _ipts([(dcx - 8, base_y - 1), (dcx - 3, base_y - 6), (dcx + 3, base_y - 6), (dcx + 8, base_y - 1)]))
                pygame.draw.polygon(
                    screen, plum_dk, _ipts([(dcx + 3, base_y - 6), (dcx + 8, base_y - 1), (dcx, base_y - 1), (dcx, base_y - 6)])
                )  # shadow right
                # tier 2 — narrow pointed cap
                pygame.draw.polygon(screen, plum, _ipts([(dcx - 3, base_y - 6), (dcx, base_y - 11), (dcx + 3, base_y - 6)]))
                pygame.draw.polygon(screen, plum_dk, _ipts([(dcx, base_y - 11), (dcx + 3, base_y - 6), (dcx, base_y - 6)]))  # shadow right
                pygame.draw.line(screen, plum_hi, (dcx, base_y - 10), (dcx, base_y - 6), 1)  # near-ridge highlight
                # needle spire + finial ball
                pygame.draw.line(screen, finial, (dcx, base_y - 11), (dcx, base_y - 17), 1)
                pygame.draw.circle(screen, finial, (dcx, base_y - 18), 1)

            _turret(sx - bw // 2 + 8)
            _turret(sx + bw // 2 - 8)

            # Central pavilion: raised brick block + slate gable (lit/shadow) + clock + cupola
            cp_y = horizon - bh - 5
            pygame.draw.rect(screen, brick, pygame.Rect(sx - 11, cp_y, 22, 5))
            pygame.draw.rect(screen, band, pygame.Rect(sx - 11, cp_y, 22, 1))
            pygame.draw.polygon(screen, slate, _ipts([(sx - 12, cp_y), (sx, cp_y - 9), (sx + 12, cp_y)]))
            pygame.draw.polygon(screen, slate_dk, _ipts([(sx, cp_y - 9), (sx + 12, cp_y), (sx, cp_y)]))  # shadow half
            pygame.draw.circle(screen, band, (sx, cp_y - 3), 3)
            pygame.draw.circle(screen, clockc, (sx, cp_y - 3), 3, 1)
            # cupola (small lantern) seated on the gable apex
            pygame.draw.rect(screen, slate, pygame.Rect(sx - 3, cp_y - 13, 6, 4))
            pygame.draw.rect(screen, slate_dk, pygame.Rect(sx, cp_y - 13, 3, 4))
            pygame.draw.rect(screen, band, pygame.Rect(sx - 3, cp_y - 13, 6, 1))
            pygame.draw.line(screen, finial, (sx, cp_y - 13), (sx, cp_y - 17), 1)
            pygame.draw.circle(screen, finial, (sx, cp_y - 18), 1)

        # Station B — Japanese JR station: viaduct-arch base, light concourse + glass,
        # big curved butterfly platform canopy, 駅名標 signboard, facade clock.
        def draw_station_modern(sx):
            wall, wall_hi, glass = (206, 210, 218), (230, 233, 239), (120, 166, 206)
            arch_d, deck = (52, 56, 70), (178, 184, 194)
            canopy, canopy_hi, post = (160, 202, 216), (222, 238, 244), (116, 124, 136)
            sign_w, sign_jr, clockc = (242, 244, 250), (40, 132, 92), (38, 42, 52)
            bw, bh = 66, 24
            body = pygame.Rect(sx - bw // 2, horizon - bh, bw, bh)
            pygame.draw.rect(screen, wall, body)
            pygame.draw.rect(screen, wall_hi, pygame.Rect(body.x, body.y, bw, 2))
            # Upper-floor glass band
            pygame.draw.rect(screen, glass, pygame.Rect(body.x + 3, body.y + 4, bw - 6, 6))
            for gx in range(body.x + 5, body.right - 4, 6):
                pygame.draw.line(screen, wall_hi, (gx, body.y + 4), (gx, body.y + 10), 1)
            # Viaduct-style arched openings at the base
            for ax in range(body.x + 4, body.right - 6, 10):
                pygame.draw.rect(screen, arch_d, pygame.Rect(ax, horizon - 10, 7, 10), border_top_left_radius=3, border_top_right_radius=3)
            # Facade clock
            pygame.draw.circle(screen, sign_w, (sx, body.y + 6), 2)
            pygame.draw.circle(screen, clockc, (sx, body.y + 6), 2, 1)
            # Big curved butterfly platform canopy on slim posts (the iconic JR roof)
            cap_y = horizon - bh - 10
            for px in (sx - 22, sx, sx + 22):
                pygame.draw.line(screen, post, (px, cap_y + 3), (px, horizon - bh), 1)
            pygame.draw.polygon(
                screen,
                canopy,
                _ipts(
                    [
                        (sx - 32, horizon - bh - 2),
                        (sx - 14, cap_y),
                        (sx + 14, cap_y),
                        (sx + 32, horizon - bh - 2),
                        (sx + 32, horizon - bh - 4),
                        (sx + 14, cap_y - 2),
                        (sx - 14, cap_y - 2),
                        (sx - 32, horizon - bh - 4),
                    ]
                ),
            )
            pygame.draw.line(screen, canopy_hi, (sx - 14, cap_y - 1), (sx + 14, cap_y - 1), 1)
            # 駅名標 — station name signboard on a post (platform side, faces the train)
            sgx = sx - bw // 2 - 7
            pygame.draw.line(screen, post, (sgx, horizon), (sgx, horizon - 10), 1)
            sign = pygame.Rect(sgx - 7, horizon - 15, 16, 6)
            pygame.draw.rect(screen, sign_w, sign)
            pygame.draw.rect(screen, sign_jr, pygame.Rect(sign.x, sign.bottom - 2, 16, 2))

        # Paint the backdrop (far → near)
        draw_fuji(j_x0 + int(jw * 0.30), horizon)
        draw_skyline(j_x0 + int(jw * 0.10), j_x0 + int(jw * 0.42), 1207)
        draw_skyline(j_x0 + int(jw * 0.58), j_x0 + int(jw * 0.88), 5530)
        draw_skytree(j_x0 + int(jw * 0.48), horizon)
        draw_tower(j_x0 + int(jw * 0.66), horizon)
        draw_station_classic(j_x0)
        draw_station_modern(j_x1)

        # ── Railway (in front of the backdrop) — slim line, runs edge-to-edge ──
        rail_x0, rail_x1 = pad, sw - pad
        pygame.draw.rect(screen, _BALLAST, pygame.Rect(rail_x0, track_y + 1, rail_x1 - rail_x0, 5), border_radius=1)
        for slx in range(rail_x0 + 6, rail_x1, 13):
            pygame.draw.rect(screen, _SLP, pygame.Rect(slx - 1, track_y + 1, 4, 5))
            pygame.draw.rect(screen, _SLP_HI, pygame.Rect(slx - 1, track_y + 1, 4, 1))
        pygame.draw.line(screen, _RAIL_DK, (rail_x0, track_y + 1), (rail_x1, track_y + 1), 1)
        pygame.draw.line(screen, _RAIL, (rail_x0, track_y), (rail_x1, track_y), 2)
        pygame.draw.line(screen, _RAIL_HI, (rail_x0, track_y - 1), (rail_x1, track_y - 1), 1)

        # ── Train motion: forward-only A → B, fade out, fade back in at A ──
        # (a train doesn't reverse down the line — each run is one journey)
        period = 7000
        tt = (pygame.time.get_ticks() % period) / period
        travel_end, fadeout_end, fadein_start = 0.70, 0.80, 0.90
        if tt < travel_end:  # A → B
            train_frac, train_alpha = tt / travel_end, 255
        elif tt < fadeout_end:  # fade out at B
            train_frac, train_alpha = 1.0, int(255 * (1 - (tt - travel_end) / (fadeout_end - travel_end)))
        elif tt < fadein_start:  # gone — repositioned at A
            train_frac, train_alpha = 0.0, 0
        else:  # fade in at A
            train_frac, train_alpha = 0.0, int(255 * (tt - fadein_start) / (1 - fadein_start))
        train_x = int(j_x0 + train_frac * jw)

        # ── Station name badges (A/B) below the rail ──────────────────────
        def draw_station_badge(sx, accent, letter):
            bfont = i18n.font(10, bold=True)
            bi = bfont.render(letter, True, (236, 242, 250))
            bw = bi.get_width() + 12
            badge = pygame.Rect(sx - bw // 2, track_y + 13, bw, 16)
            pygame.draw.rect(screen, (54, 60, 74), badge, border_radius=4)
            pygame.draw.rect(screen, accent, badge, width=1, border_radius=4)
            screen.blit(bi, (sx - bi.get_width() // 2, badge.centery - bi.get_height() // 2))
            return badge.bottom

        stn_bottom = draw_station_badge(j_x0, (140, 148, 162), i18n.t("setup.ocr_disclaimer.journey.station_a"))
        draw_station_badge(j_x1, _ARR, i18n.t("setup.ocr_disclaimer.journey.station_b"))

        # ── Trigger markers + labels + pass-glow ─────────────────────────
        label_top_y = y + 2
        _trigger_defs = [
            (dep_x, _DEP, "setup.ocr_disclaimer.journey.departure", ">30 km/h"),
            (appr_x, _APPR, "setup.ocr_disclaimer.journey.approach", f"~{self.lead_m} m"),
            (arr_x, _ARR, "setup.ocr_disclaimer.journey.arrival", None),
        ]
        for tx, col, key, cond in _trigger_defs:
            # Glow = train proximity to this trigger, scaled by train visibility
            glow = max(0.0, 1.0 - abs(train_x - tx) / 44.0) * (train_alpha / 255.0)
            mark_y = rail_top
            if glow > 0:
                ring_r = int(7 + (1 - glow) * 12)
                halo = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(halo, (*col, int(glow * 150)), (ring_r + 2, ring_r + 2), ring_r, 2)
                pygame.draw.circle(halo, (*col, int(glow * 90)), (ring_r + 2, ring_r + 2), max(1, ring_r - 5))
                screen.blit(halo, (tx - ring_r - 2, mark_y - ring_r - 2))
            # Trigger annotation — name + condition stacked together at the TOP
            lbl_col = tuple(min(255, int(c + glow * (255 - c))) for c in col)
            lbl_img = cap_font.render(i18n.t(key), True, lbl_col)
            lbl_x = min(tx - lbl_img.get_width() // 2, sw - pad - lbl_img.get_width())
            screen.blit(lbl_img, (lbl_x, label_top_y))
            ann_btm = label_top_y + lbl_img.get_height()
            if cond:
                ci = cap_font.render(cond, True, self.dim_color)
                ci_x = min(tx - ci.get_width() // 2, sw - pad - ci.get_width())
                screen.blit(ci, (ci_x, ann_btm + 1))
                ann_btm += 1 + ci.get_height()
            # Connector + dot (dep/appr only — B's station is its own marker)
            if tx != arr_x:
                tgt_y = mark_y - 8
                if tgt_y > ann_btm + 2:
                    pygame.draw.line(screen, col, (tx, ann_btm + 1), (tx, tgt_y), 1)
                dot_r = 5 + int(glow * 2)
                pygame.draw.circle(screen, col, (tx, mark_y), dot_r)
                pygame.draw.circle(screen, (42, 46, 58), (tx, mark_y), dot_r - 2)

        # ── Animated train (drawn last so it rides over markers) ──────────
        if self._disclaimer_train is None:
            try:
                _p = project_root() / "data" / "disclaimer" / "suica_train.png"
                self._disclaimer_train = pygame.image.load(str(_p)).convert_alpha() if _p.exists() else False
            except Exception:
                self._disclaimer_train = False

        if self._disclaimer_train is not False and train_alpha > 0:
            raw = self._disclaimer_train
            rw, rh = raw.get_size()
            target_h = 48
            sc = target_h / rh
            tr = pygame.transform.smoothscale(raw, (max(1, int(rw * sc)), target_h))
            if train_alpha < 255:
                tr = tr.copy()
                tr.set_alpha(train_alpha)
            # Wheels on the rail; penguin (frontmost) rides over the markers
            screen.blit(tr, (train_x - tr.get_width() // 2, rail_bot - tr.get_height()))
        elif self._disclaimer_train is False:
            tw, th = 48, 18
            pygame.draw.rect(screen, (205, 210, 215), pygame.Rect(train_x - tw // 2, rail_bot - th, tw, th), border_radius=2)

        y = stn_bottom + 14
        # Misfire caveat — belongs with the firing behavior the diagram shows.
        beta_img = body_font.render(i18n.t("setup.ocr_disclaimer.beta"), True, self.dim_color)
        screen.blit(beta_img, (pad, y))
        y += beta_img.get_height() + 18

        # Divider + Privacy & consent section
        pygame.draw.line(screen, border_color, (pad, y), (sw - pad, y))
        y += 16
        t_img = subhead_font.render(i18n.t("setup.ocr_disclaimer.terms_heading"), True, heading_color)
        screen.blit(t_img, (pad, y))
        y += t_img.get_height() + 10

        full_w = sw - 2 * pad
        bullet_px = body_font.size("· ")[0]
        bullet_w = full_w - bullet_px

        def render_bullet(text, color):
            nonlocal y
            lines = wrap_text(body_font, text, bullet_w)
            for j, line in enumerate(lines):
                img = body_font.render(("· " if j == 0 else "  ") + line, True, color)
                screen.blit(img, (pad, y))
                y += img.get_height() + 2

        for para in i18n.t("setup.ocr_disclaimer.consent").split("\n"):
            if para:
                render_bullet(para, self.text_color)
        y += 6

        for para in i18n.t("setup.ocr_disclaimer.privacy").split("\n"):
            if para:
                render_bullet(para, self.text_color)
        y += 24  # bottom padding in content

        content_height = (y + scroll_y) - (clip_top + 16)
        max_scroll = max(0, content_height - clip_h)

        screen.set_clip(None)

        # ── Scroll indicator ───────────────────────────────────────────────
        if max_scroll > 0:
            sb_x, sb_w = sw - 10, 5
            track_top, track_h = clip_top + 4, clip_h - 8
            thumb_h = max(20, int((clip_h / content_height) * track_h))
            ratio = scroll_y / max_scroll
            thumb_y = track_top + int(ratio * (track_h - thumb_h))
            pygame.draw.rect(screen, (60, 66, 80), pygame.Rect(sb_x, track_top, sb_w, track_h), border_radius=3)
            pygame.draw.rect(screen, (130, 140, 160), pygame.Rect(sb_x, thumb_y, sb_w, thumb_h), border_radius=3)

        # ── Fixed footer ───────────────────────────────────────────────────
        footer_top = sh - footer_h
        pygame.draw.line(screen, border_color, (pad, footer_top + 1), (sw - pad, footer_top + 1))

        ok_unlocked = scroll_y >= max_scroll - 2
        ok_color = self.highlight_color if ok_unlocked else self.control_dim
        ok_rect = pygame.Rect(sw - pad - btn_w, footer_top + (footer_h - btn_h) // 2, btn_w, btn_h)
        cancel_rect = pygame.Rect(ok_rect.x - btn_gap - btn_w, ok_rect.y, btn_w, btn_h)

        btn_font = i18n.font(13, bold=True)
        pygame.draw.rect(screen, self.control_bg, cancel_rect, border_radius=btn_h // 2)
        c_img = btn_font.render(i18n.t("setup.ocr_disclaimer.cancel"), True, self.text_color)
        screen.blit(c_img, (cancel_rect.centerx - c_img.get_width() // 2, cancel_rect.centery - c_img.get_height() // 2))

        pygame.draw.rect(screen, ok_color, ok_rect, border_radius=btn_h // 2)
        ok_img = btn_font.render(i18n.t("setup.ocr_disclaimer.ok"), True, self.text_color)
        screen.blit(ok_img, (ok_rect.centerx - ok_img.get_width() // 2, ok_rect.centery - ok_img.get_height() // 2))

        if not ok_unlocked:
            hint_img = cap_font.render(i18n.t("setup.ocr_disclaimer.scroll_hint"), True, self.dim_color)
            screen.blit(hint_img, (pad, ok_rect.centery - hint_img.get_height() // 2))

        return ok_rect, cancel_rect, max_scroll

    def _show_ocr_disclaimer(self) -> bool:
        """Show OCR disclaimer/consent modal on toggle OFF→ON.
        Resizes the pygame window to the popup dimensions, then restores.
        OK is locked until the user scrolls to the bottom of the consent text.
        Returns True (accepted) or False (cancelled / ESC / window close)."""
        old_size = self.screen.get_size()
        popup_surf = pygame.display.set_mode((720, 560))

        clock = pygame.time.Clock()
        scroll_y = 0
        running = True
        accepted = False
        while running:
            clock.tick(60)
            popup_surf.fill((42, 46, 58))
            ok_rect, cancel_rect, max_scroll = self._draw_ocr_disclaimer_panel(popup_surf, scroll_y)
            ok_unlocked = scroll_y >= max_scroll - 2
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.event.post(event)
                    running = False
                elif event.type == pygame.MOUSEWHEEL:
                    scroll_y = max(0, min(max_scroll, scroll_y - event.y * 20))
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_RETURN and ok_unlocked:
                        accepted = True
                        running = False
                    elif event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                        scroll_y = min(max_scroll, scroll_y + 40)
                    elif event.key in (pygame.K_UP, pygame.K_PAGEUP):
                        scroll_y = max(0, scroll_y - 40)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if ok_rect.collidepoint(event.pos) and ok_unlocked:
                        accepted = True
                        running = False
                    elif cancel_rect.collidepoint(event.pos):
                        running = False

        self.screen = pygame.display.set_mode(old_size)
        return accepted

    def _handle_band_click(self, pos: tuple[int, int]) -> bool:
        """Dispatch a mouse click to the OCR Auto-PA band. Returns True if any
        control was hit (caller can stop propagation / suppress sound)."""
        if self._toggle_rect and self._toggle_rect.collidepoint(pos):
            if not self.auto_input_enabled:
                if self._show_ocr_disclaimer():
                    self.auto_input_enabled = True
            else:
                self.auto_input_enabled = False
            s = i18n.load_settings()
            s["auto_input"] = self.auto_input_enabled
            i18n.save_settings(s)
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
            (rect.centerx - label_img.get_width() // 2, rect.centery - label_img.get_height() // 2),
        )
        self._tutorial_btn_rect = rect

    def _draw_update_hint(self) -> None:
        """Render a small clickable "update available" hint in the top-left when
        ``update_check`` found a newer GitHub release. Sets ``_update_hint_rect``
        / ``_update_url`` for the click handler. No-op (clears them) when no
        update is pending — including offline / failed checks (fail-silent)."""
        info = update_check.get_update()
        if info is None:
            self._update_hint_rect = None
            self._update_url = None
            return
        version, url = info
        self._update_url = url
        # ── tuneable params ──────────────────────────────────────
        margin_left = 12
        margin_top = 12
        pill_h = 28
        pad_x = 12
        dot_r = 5
        dot_gap = 7  # gap between status dot and label
        # ─────────────────────────────────────────────────────────
        label = i18n.t("setup.update_hint", version=version)
        label_img = self.control_font.render(label, True, self.text_color)
        pill_w = pad_x + dot_r * 2 + dot_gap + label_img.get_width() + pad_x
        rect = pygame.Rect(margin_left, margin_top, pill_w, pill_h)
        pygame.draw.rect(self.screen, self.control_bg, rect, border_radius=pill_h // 2)
        cy = rect.centery
        dot_cx = rect.x + pad_x + dot_r
        pygame.draw.circle(self.screen, self.highlight_color, (dot_cx, cy), dot_r)
        self.screen.blit(label_img, (dot_cx + dot_r + dot_gap, cy - label_img.get_height() // 2))
        self._update_hint_rect = rect

    def _load_line_icon(self, line_code: str) -> pygame.Surface | None:
        """Load and cache a line icon PNG from data/line_icons/.

        Returns the scaled surface, or None if the icon file doesn't exist.
        Aspect ratio is preserved; height is fixed to ``_line_icon_h``."""
        if line_code in self._line_icon_cache:
            return self._line_icon_cache[line_code]
        path = project_root() / "data" / "line_icons" / f"{line_code}.png"
        if not path.exists():
            self._line_icon_cache[line_code] = None
            return None
        img = pygame.image.load(str(path)).convert_alpha()
        sw, sh = img.get_size()
        target_w = int(round(sw * (self._line_icon_h / sh)))
        scaled = pygame.transform.smoothscale(img, (target_w, self._line_icon_h))
        self._line_icon_cache[line_code] = scaled
        return scaled

    def _draw_line_badge(self, x: int, cy: int, line_code: str) -> int:
        """Draw a JR line badge from the authentic PNG icon set. Vertically
        centered at `cy`. Returns the right-edge x for placing subsequent
        content — when line_code is empty or icon is missing, no badge is
        drawn and `x` is returned unchanged so text isn't pushed right by
        a phantom badge width."""
        if not line_code:
            return x
        icon = self._load_line_icon(line_code)
        if icon is None:
            return x
        icon_w, icon_h = icon.get_size()
        self.screen.blit(icon, (x, cy - icon_h // 2))
        return x + icon_w

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

    def _get_route_index_at_pos(self, pos: tuple[int, int]) -> int | None:
        """Resolve a screen coordinate to a route list index, if within bounds."""
        mx, my = pos
        # Check horizontal bounds (row width is screen_width - 40, starting at x=20)
        if 20 <= mx <= self.screen.get_width() - 20:
            # Check vertical bounds of currently drawn visible route list rows
            list_top = 70
            num_drawn = min(self.max_visible, len(self.routes) - self.scroll_offset)
            list_bottom = list_top + num_drawn * self.row_height
            if list_top <= my < list_bottom:
                idx = self.scroll_offset + (my - list_top) // self.row_height
                if 0 <= idx < len(self.routes):
                    return idx
        return None

    def _handle_scroll(self, scroll_amount: int) -> None:
        """Handle list viewport scrolling and update selection under cursor."""
        max_offset = max(0, len(self.routes) - self.max_visible)
        self.scroll_offset = max(0, min(max_offset, self.scroll_offset + scroll_amount))

        # Update selection based on cursor position
        m_pos = pygame.mouse.get_pos()
        hovered_idx = self._get_route_index_at_pos(m_pos)
        if hovered_idx is not None:
            self.selected_idx = hovered_idx
        else:
            # Not over the list, clamp selected_idx to the new visible area to prevent viewport snap-back
            self.selected_idx = max(self.scroll_offset, min(self.selected_idx, self.scroll_offset + self.max_visible - 1))
            self.selected_idx = max(0, min(len(self.routes) - 1, self.selected_idx))

    def _confirm_route_selection(self, selected: dict) -> dict | None:
        """Load full route data and return selection config."""
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
        clock = pygame.time.Clock()

        try:
            while running:
                clock.tick(60)
                self.draw(self.selected_idx)

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return None
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1:
                            # ? Tutorial button takes priority — sits above the
                            # OCR auto-PA band, so check it first.
                            if self._tutorial_btn_rect is not None and self._tutorial_btn_rect.collidepoint(event.pos):
                                return {"action": "run_tutorial"}

                            # Update-available hint → open the release page in
                            # the default browser. Fail-silent if it can't open.
                            if self._update_hint_rect is not None and self._update_hint_rect.collidepoint(event.pos) and self._update_url:
                                try:
                                    webbrowser.open(self._update_url)
                                except Exception:
                                    pass
                                continue

                            # Check if click is on route list
                            clicked_idx = self._get_route_index_at_pos(event.pos)
                            if clicked_idx is not None:
                                self.selected_idx = clicked_idx
                                selected = self.routes[self.selected_idx]
                                return self._confirm_route_selection(selected)

                            self._handle_band_click(event.pos)
                            continue

                    elif event.type == pygame.MOUSEWHEEL:
                        # Modern mouse wheel support
                        self._handle_scroll(-event.y)
                        continue

                    elif event.type == pygame.MOUSEMOTION:
                        # Motion guard
                        if event.pos != self._last_mouse_pos:
                            self._last_mouse_pos = event.pos
                            hovered_idx = self._get_route_index_at_pos(event.pos)
                            if hovered_idx is not None:
                                self.selected_idx = hovered_idx

                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            return None
                        elif event.key == pygame.K_UP:
                            self.selected_idx = max(0, self.selected_idx - 1)
                        elif event.key == pygame.K_DOWN:
                            self.selected_idx = min(len(self.routes) - 1, self.selected_idx + 1)
                        elif event.key == pygame.K_RETURN:
                            if self.routes:
                                selected = self.routes[self.selected_idx]
                                return self._confirm_route_selection(selected)
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

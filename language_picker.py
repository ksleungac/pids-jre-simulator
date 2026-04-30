"""First-run language picker. Runs before the setup screen if settings.json
has no language set yet. Three self-labeled rows; OS-locale auto-highlighted
but not auto-confirmed; hover/arrow re-renders chrome in the highlighted
language so the user previews the choice before confirming."""

import pygame

import i18n


class LanguagePicker:
    """Pick one of i18n.SUPPORTED_LANGS. Returns the chosen code, or None on quit/ESC.

    Each row's label is locked to its own script's primary font so fonts don't
    jump as the user hovers. Arial 28pt and CJK 24pt produce matching ~32px
    rendered heights (Arial measures ~84% of CJK height at the same point size).
    """

    # (code, label, font_name, font_size) — sizes pre-tuned to match rendered height.
    LANGS = [
        ("en",    "English",  "arial",         28),
        ("zh_HK", "繁體中文", "microsoftyahei", 24),
        ("zh_CN", "简体中文", "microsoftyahei", 24),
    ]

    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        default = i18n.detect_default_lang()
        self.selected_idx = next(
            (i for i, row in enumerate(self.LANGS) if row[0] == default), 0
        )
        i18n.set_language(self.LANGS[self.selected_idx][0])

        # Palette mirrors SetupScreen for visual consistency across chrome.
        self.bg_color = (62, 68, 80)
        self.text_color = (240, 242, 248)
        self.highlight_color = (96, 168, 84)
        self.dim_color = (175, 182, 195)
        self.row_bg = (88, 96, 112)

        self._row_rects: list[pygame.Rect] = []
        self._ok_rect: pygame.Rect | None = None

    def _on_select(self, idx: int) -> None:
        self.selected_idx = idx
        i18n.set_language(self.LANGS[idx][0])

    def draw(self) -> None:
        self.screen.fill(self.bg_color)
        w, _ = self.screen.get_size()

        # ── tuneable params ────────────────────────────────────────────────
        title_y = 30
        row_top = 100
        row_h = 50
        row_gap = 18
        row_margin = 80
        ok_y = 310
        ok_w, ok_h = 120, 40
        hint_y = 380
        # ────────────────────────────────────────────────────────────────────

        # Picker chrome (title, OK button, hint) locks to JhengHei — handles all
        # three scripts and stays put when the active language changes on hover.
        title_font = i18n.font_named("microsoftjhenghei", 28, bold=True)
        btn_font = i18n.font_named("microsoftjhenghei", 20, bold=True)
        hint_font = i18n.font_named("microsoftjhenghei", 14, bold=True)

        title = title_font.render(i18n.t("picker.title"), True, self.text_color)
        self.screen.blit(title, ((w - title.get_width()) // 2, title_y))

        self._row_rects = []
        for i, (_, label, font_name, font_size) in enumerate(self.LANGS):
            y = row_top + i * (row_h + row_gap)
            rect = pygame.Rect(row_margin, y, w - 2 * row_margin, row_h)
            self._row_rects.append(rect)
            bg = self.highlight_color if i == self.selected_idx else self.row_bg
            pygame.draw.rect(self.screen, bg, rect, border_radius=8)
            row_font = i18n.font_named(font_name, font_size, bold=True)
            label_img = row_font.render(label, True, self.text_color)
            self.screen.blit(
                label_img,
                (rect.centerx - label_img.get_width() // 2, rect.centery - label_img.get_height() // 2),
            )

        self._ok_rect = pygame.Rect((w - ok_w) // 2, ok_y, ok_w, ok_h)
        pygame.draw.rect(self.screen, self.highlight_color, self._ok_rect, border_radius=ok_h // 2)
        ok_img = btn_font.render(i18n.t("picker.confirm"), True, self.text_color)
        self.screen.blit(
            ok_img,
            (self._ok_rect.centerx - ok_img.get_width() // 2, self._ok_rect.centery - ok_img.get_height() // 2),
        )

        hint = hint_font.render(i18n.t("picker.hint"), True, self.dim_color)
        self.screen.blit(hint, ((w - hint.get_width()) // 2, hint_y))

        pygame.display.flip()

    def run(self) -> str | None:
        while True:
            self.draw()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key == pygame.K_UP:
                        self._on_select((self.selected_idx - 1) % len(self.LANGS))
                    elif event.key == pygame.K_DOWN:
                        self._on_select((self.selected_idx + 1) % len(self.LANGS))
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return self.LANGS[self.selected_idx][0]
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = event.pos
                    for i, rect in enumerate(self._row_rects):
                        if rect.collidepoint(pos):
                            self._on_select(i)
                            break
                    if self._ok_rect and self._ok_rect.collidepoint(pos):
                        return self.LANGS[self.selected_idx][0]

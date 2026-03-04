"""Setup screen for route and train selection."""

import os
import json
import pygame


class SetupScreen:
    """Handles route and train selection before starting the simulator."""

    def __init__(self, screen: pygame.Surface):
        """Initialize the setup screen.

        Args:
            screen: Pygame surface to draw on
        """
        self.screen = screen
        self.routes = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.row_height = 50
        # Calculate how many routes fit on screen (accounting for title and instructions)
        available_height = screen.get_height() - 100  # 20px title + 20px top + 60px bottom
        self.max_visible = max(5, available_height // self.row_height)

        # Fonts
        self.title_font = pygame.font.SysFont("shingopr6nmedium", 28)
        self.route_font = pygame.font.SysFont("shingopr6nmedium", 20)
        self.instruction_font = pygame.font.SysFont("shingopr6nmedium", 16)

        # Colors
        self.bg_color = (30, 30, 30)
        self.text_color = (255, 255, 255)
        self.highlight_color = (116, 193, 30)
        self.dim_color = (150, 150, 150)

    def scan_routes(self, base_dir: str = "audio") -> list:
        """Scan for available routes by finding route.json files.

        Groups routes by name, then by train diagram.
        Extracts diagram from folder name when available (e.g., nanbu/4027F/route.json).

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

                        # Extract diagram from folder name (e.g., "4027F" from "nanbu/4027F")
                        rel_path = os.path.relpath(root, base_dir)
                        path_parts = rel_path.split(os.sep)
                        folder_diagram = ""
                        if len(path_parts) > 1:
                            # Use the last subfolder name as diagram (e.g., "4027F", "916H")
                            folder_diagram = path_parts[-1]

                        # Prefer folder name for diagram, fallback to JSON
                        diagram = folder_diagram if folder_diagram else route_data.get("diagram", "")

                        self.routes.append(
                            {
                                "path": root,
                                "name": route_data.get("route", "Unknown"),
                                "diagram": diagram,
                                "type": route_data.get("type", ""),
                                "dest": route_data.get("dest", ""),
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
        title = "路線を選択 (Select Route)"
        title_img = self.title_font.render(title, True, self.text_color)
        title_x = (self.screen.get_width() - title_img.get_width()) // 2
        self.screen.blit(title_img, (title_x, 20))

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

            # Build display text - consistent format:
            # Line 1: Route name - Train diagram (if exists)
            # Line 2: Train type | Destination ゆき
            if diagram:
                line1 = f"{route_name} - {diagram}"
            else:
                line1 = route_name

            # Line 2: Type and destination
            line2_parts = []
            if route_type:
                line2_parts.append(route_type)
            if dest:
                line2_parts.append(f"{dest} ゆき")
            line2 = "  |  ".join(line2_parts) if line2_parts else ""

            # Check if selected
            is_selected = i == selected_idx

            if is_selected:
                # Draw highlight background (taller to cover both lines)
                highlight_rect = pygame.Rect(20, y_offset + display_idx * self.row_height - 5, self.screen.get_width() - 40, self.row_height)
                pygame.draw.rect(self.screen, self.highlight_color, highlight_rect, border_radius=5)
                text_color = (255, 255, 255)
            else:
                text_color = self.text_color

            # Draw route name
            line1_img = self.route_font.render(line1, True, text_color)
            self.screen.blit(line1_img, (40, y_offset + display_idx * self.row_height))

            # Draw secondary info
            if line2:
                line2_img = self.route_font.render(line2, True, self.dim_color if not is_selected else (200, 200, 200))
                self.screen.blit(line2_img, (60, y_offset + display_idx * self.row_height + 22))

        # Draw scrollbar if there are more routes than visible
        if len(self.routes) > self.max_visible:
            self._draw_scrollbar()

        # Draw instructions (centered at bottom)
        instructions = "↑↓: 移動 (Navigate)  |  Enter: 決定 (Select)  |  ESC: キャンセル (Cancel)"
        inst_img = self.instruction_font.render(instructions, True, self.dim_color)
        inst_x = (self.screen.get_width() - inst_img.get_width()) // 2
        self.screen.blit(inst_img, (inst_x, self.screen.get_height() - 35))

        pygame.display.flip()

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
        """Run the setup screen loop. Returns configuration or None if cancelled.

        Returns:
            dict with {"work_dir": path, "route_data": data} when confirmed
            None if user cancels (ESC)
        """
        self.scan_routes()

        if not self.routes:
            print("No routes found. Please add route.json files to the audio/ directory.")
            return None

        running = True

        while running:
            self.draw(self.selected_idx)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
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
                                return {"work_dir": selected["path"], "route_data": route_data}
                            except Exception as e:
                                print(f"Error loading route data: {e}")
                                return None

        return None

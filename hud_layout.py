"""HUD region constants for JR EAST Train Simulator at 2560x1440 native resolution.

Single source of truth for cell positions. Cell coordinates are HUD-relative
(within the 350x480 HUD crop), not screen-relative — this way only HUD_BBOX
needs to change for other resolutions.
"""

# Full HUD bounding box on the 2560x1440 game window (x, y, w, h)
HUD_BBOX = (2200, 20, 350, 480)

# Cells within the HUD crop (HUD-relative coordinates)
# Value cells contain the right-aligned numeric+unit text only (label excluded).
DISTANCE_VALUE_BBOX = (120, 314, 230, 55)
SPEED_VALUE_BBOX = (120, 165, 230, 55)
# Speed-limit (最高速度) row — red digits + dark "km/h" suffix. Sits between speed
# and distance rows. Reader uses red color mask; suffix is dark so excluded by the mask.
SPEED_LIMIT_VALUE_BBOX = (120, 215, 230, 55)
# Badge area (Next/次停車駅 vs Stopping at/停車中). Same green pentagon shape across states;
# only the text inside differs. Classified via pixel-diff against anchor templates.
# Left + top edges trimmed off the original cell's scenery bleed-through zone (translucent
# HUD bg over varying scene): the leftmost ~13 px and top ~5 px were pure noise outside
# the pentagon's body. The trim point sits where the pentagon's left curve / top edge
# begins, keeping all text content in-frame.
BADGE_BBOX = (29, 122, 111, 40)

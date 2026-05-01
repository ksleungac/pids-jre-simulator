"""One-off: stack IRL Tokyo PIDS reference above the current render."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

REF = "lcd_references/transfer_tokyo.png"
RENDER = "_visual_iter/v_tokyo.png"
OUT = "_visual_iter/v_tokyo_compare.png"
LABEL = "RENDER"

pygame.init()
pygame.display.set_mode((1, 1))

ref = pygame.image.load(REF).convert_alpha()
ren = pygame.image.load(RENDER).convert_alpha()

target_w = ref.get_width()
new_h = int(round(ren.get_height() * target_w / ren.get_width()))
ren = pygame.transform.smoothscale(ren, (target_w, new_h))

BAND = 32
BORDER = 8
BG = (34, 34, 34)
WHITE = (255, 255, 255)
font = pygame.font.SysFont("arial", 18, bold=False)

total_w = target_w + 2 * BORDER
total_h = (BAND + ref.get_height()) + (BAND + ren.get_height()) + 2 * BORDER

out = pygame.Surface((total_w, total_h))
out.fill(BG)

y = BORDER
lbl1 = font.render("REFERENCE (IRL Tokyo PIDS, JO train)", True, WHITE)
out.blit(lbl1, ((total_w - lbl1.get_width()) // 2, y + (BAND - lbl1.get_height()) // 2))
y += BAND
out.blit(ref, (BORDER, y))
y += ref.get_height()

lbl2 = font.render(LABEL, True, WHITE)
out.blit(lbl2, ((total_w - lbl2.get_width()) // 2, y + (BAND - lbl2.get_height()) // 2))
y += BAND
out.blit(ren, (BORDER, y))

pygame.image.save(out, OUT)
print(f"Saved {OUT} ({total_w}x{total_h})")

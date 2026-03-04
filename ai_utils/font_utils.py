"""
Font measurement utilities for JRE-PA-Simulator.

Usage:
    .venv/Scripts/python ai_utils/font_utils.py

Measures ShinGoPr6N-Medium font dimensions at various sizes
and outputs results to ai_utils/font_metrics.txt
"""

import pygame
import sys
from pathlib import Path

pygame.init()

# Font path relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
FONT_PATH = PROJECT_ROOT / 'fonts' / 'ShinGoPr6N-Medium.otf'

if not FONT_PATH.exists():
    print(f"Error: Font not found at {FONT_PATH}")
    sys.exit(1)

# Test characters using unicode escapes to avoid encoding issues
TEST_CHARS = [
    ('A', 'Latin A'),
    ('W', 'Latin W'),
    ('i', 'Latin i'),
    ('1', 'Digit 1'),
    ('\u5c71', 'Kanji: mountain'),
    ('\u624b', 'Kanji: hand'),
    ('\u7dda', 'Kanji: line'),
    ('\u3042', 'Hiragana: a'),
    ('\u30a2', 'Katakana: a'),
]

# Station name examples
STATION_NAMES = [
    ('\u6771\u4eac\u99c5', '3 chars: Tokyo Station'),
    ('\u5c71\u624b\u7dda', '3 chars: Yamanote Line'),
    ('\u65b0\u5bbf\u5fa1\u82d1\u524d', '5 chars: Shinjuku-gyoemmae'),
    ('\u6771\u4eac\u30c6\u30ec\u30dd\u30fc\u30c8', '7 chars: Tokyo Teleport'),
]

results = []
results.append(f"=== Font Metrics for ShinGoPr6N-Medium ===")
results.append(f"Font path: {FONT_PATH}\n")

# Test multiple sizes
for size in [12, 16, 20, 24, 32, 48, 78]:
    font = pygame.font.Font(str(FONT_PATH), size)
    results.append(f'\n=== Size {size} ===')
    results.append(f'Height: {font.get_height()}')
    results.append(f'Ascent: {font.get_ascent()}')
    results.append(f'Descent: {font.get_descent()}')
    results.append(f'Line spacing: {font.get_linesize()}')

    for char, label in TEST_CHARS:
        width, height = font.size(char)
        results.append(f'  {label}: {width}x{height}')

# Station name analysis at size 78
results.append('\n\n=== Station Names at FONT_STATION_SIZE=78 ===')
font_78 = pygame.font.Font(str(FONT_PATH), 78)

# Upper LCD station area width
S_WIDTH = 730
station_width = int(S_WIDTH * 0.54)  # 394px
results.append(f'Screen width: {S_WIDTH}')
results.append(f'Station area width (54%): {station_width}\n')

for name, label in STATION_NAMES:
    total_w, total_h = font_78.size(name)
    char_count = len(name)
    avg_w = total_w / char_count

    if total_w > station_width:
        scale = station_width / total_w
        action = f"COMPRESS to {scale:.0%}"
    else:
        action = "EXPAND (add spacing)"

    results.append(f'{label}')
    results.append(f'  Original: {total_w}x{total_h}px ({char_count} chars, avg {avg_w:.0f}px/char)')
    results.append(f'  Action: {action} to fit {station_width}px\n')

# Write to file
output_path = PROJECT_ROOT / 'ai_utils' / 'font_metrics.txt'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print('\n'.join(results))
print(f'\nResults saved to {output_path}')

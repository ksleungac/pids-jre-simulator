import pygame
pygame.init()

font_path = 'fonts/ShinGoPr6N-Medium.otf'
font = pygame.font.Font(font_path, 78)

results = []

results.append('=== ShinGoPr6N-Medium at FONT_STATION_SIZE=78 ===\n')

# Test with different character counts
test_cases = [
    ('3 chars (Kanji)', '\u6771\u4eac\u99c5'),  # 東京駅
    ('3 chars (Mixed)', '\u5c71\u624b\u7dda'),  # 山手線
    ('5 chars (Kanji)', '\u6771\u4eac\u56fd\u969b\u7a7a\u6e2f'),  # 東京国際空港
    ('5 chars (Mixed)', '\u65b0\u5bbf\u5fa1\u82d1\u524d'),  # 新宿御苑前
    ('7 chars', '\u6771\u4eac\u30c6\u30ec\u30dd\u30fc\u30c8'),  # 東京テレポート
    ('7 chars (Long)', '\u6210\u7530\u7a7a\u6e2f\u7b2c\uff11\u30bf\u30fc\u30df\u30ca\u30eb'),  # 成田空港第１ターミナル
]

results.append('Individual character measurements:')
single_chars = [
    ('\u6771', 'Kanji: east'),
    ('\u4eac', 'Kanji: capital'),
    ('\u99c5', 'Kanji: station'),
    ('\u5c71', 'Kanji: mountain'),
    ('\u624b', 'Kanji: hand'),
    ('\u7dda', 'Kanji: line'),
    ('\u30c6', 'Katakana: te'),
    ('\u30ec', 'Katakana: re'),
    ('\u30dd', 'Katakana: po'),
    ('A', 'Latin A'),
    ('1', 'Digit 1'),
]
for char, label in single_chars:
    w, h = font.size(char)
    results.append(f'  {label}: {w}x{h} pixels')

results.append('\nFull station name measurements:')
for label, text in test_cases:
    total_w, total_h = font.size(text)
    avg_char_w = total_w / len(text)
    results.append(f'  {label}:')
    results.append(f'    Total: {total_w}x{total_h} pixels')
    results.append(f'    Avg per char: {avg_char_w:.1f}x{total_h} pixels')

results.append('\n=== Upper LCD Station Area ===')
from constants import S_WIDTH, FONT_STATION_SIZE
station_area_width = int(S_WIDTH * 0.54)
results.append(f'Screen width: {S_WIDTH}')
results.append(f'Station area width (54%): {station_area_width}')
results.append(f'Font size: {FONT_STATION_SIZE}')

# Calculate scaling ratios
results.append('\n=== Scaling Analysis ===')
for label, text in test_cases:
    total_w, total_h = font.size(text)
    scale_ratio = station_area_width / total_w
    results.append(f'  {label}: Scaled to {station_area_width}w = {scale_ratio:.2%} horizontal ratio')

# Write to file
with open('font_station_metrics.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print('\n'.join(results))
print('\nResults saved to font_station_metrics.txt')

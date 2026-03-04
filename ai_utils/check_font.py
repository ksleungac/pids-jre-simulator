import pygame
import sys
pygame.init()

font_path = 'fonts/ShinGoPr6N-Medium.otf'

# Test characters using unicode
test_chars = [
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

results = []

# Test multiple sizes
for size in [12, 16, 20, 24, 32, 48]:
    font = pygame.font.Font(font_path, size)
    results.append(f'\n=== Size {size} ===')
    results.append(f'Height: {font.get_height()}')
    results.append(f'Ascent: {font.get_ascent()}')
    results.append(f'Descent: {font.get_descent()}')
    results.append(f'Line spacing: {font.get_linesize()}')

    for char, label in test_chars:
        width, height = font.size(char)
        results.append(f'  {label}: {width}x{height}')

# Write to file to avoid encoding issues
with open('font_metrics.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print('\n'.join(results))
print('\nResults also saved to font_metrics.txt')

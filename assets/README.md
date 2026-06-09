# assets/

README screenshots for all three READMEs (EN / zh-HK / zh-CN).

**When updating screenshots, treat as a data task — read before regenerating:**

- `audio/README.md` — per-line layout (some lines non-standard, e.g. Yamanote is flat with no diagram subfolder)
- `DATA_FORMAT.md` — where data lives (transfers → `data/stations.json` keyed by station name, not `route.json` stops)

## Files

| File | What it shows | How to regenerate |
|---|---|---|
| `01-keihin-tohoku-compact.png` | Keihin-Tohoku 8-station compact view at Omiya | `uv run preview_display.py --route audio/keihin/1275A/route.json --stop 0 --lower-view eight --screenshot assets/01-keihin-tohoku-compact.png` |
| `02-sobu-skip-animation.png` | Sobu skip animation (次は都賀, 東千葉 skipped) | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 11 --pa 0 --lower-view eight --screenshot assets/02-sobu-skip-animation.png` |
| `03-sobu-full-route.png` | Sobu full-route view at Tokyo | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 0 --lower-view full --screenshot assets/03-sobu-full-route.png` |
| `04-tokyo-transfer-info.png` | Tokyo transfer panel (JO19) | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 0 --lower-view transfer --screenshot assets/04-tokyo-transfer-info.png` |
| `05-shinjuku-transfer-info.png` | Shinjuku transfer panel (JY17) | `uv run preview_display.py --route audio/yamanote/route.json --stop 22 --lower-view transfer --screenshot assets/05-shinjuku-transfer-info.png` |
| `06-setup-screen.png` | Setup screen scrolled 3 rows | `uv run preview_chrome.py setup --selected 7 --out assets/06-setup-screen.png` |

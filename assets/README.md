# assets/

README screenshots for all three READMEs (EN / zh-HK / zh-CN).

**Naming:** `NN-kebab-descriptor.png` — zero-padded 2-digit sequence + kebab-case descriptor. Every entry needs a reproducible regen command in the table below; for a state the preview CLI can't reach (a committed route, a single picker sub-screen), add a committed `_dev_scripts/` helper rather than a throwaway script.

**When updating screenshots, treat as a data task — read before regenerating:**

- `audio/README.md` — per-line layout. Every shipped line is pooled: `audio/<line>/{pa,sta}/` shared, `audio/<line>/<diagram>/route.json` carrying `"audio_root": ".."`
- `DATA_FORMAT.md` — where data lives (transfers → `data/stations.json` keyed by station name, not `route.json` stops)

## Files

| File | What it shows | How to regenerate |
|---|---|---|
| `01-keihin-tohoku-compact.png` | Keihin-Tohoku 8-station compact view at Omiya | `uv run preview_display.py --route audio/keihin/1275A/route.json --stop 0 --lower-view eight --screenshot assets/01-keihin-tohoku-compact.png` |
| `02-sobu-skip-animation.png` | Sobu skip animation (次は都賀, 東千葉 skipped) | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 11 --pa 0 --lower-view eight --screenshot assets/02-sobu-skip-animation.png` |
| `03-sobu-full-route.png` | Sobu full-route view at Tokyo | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 0 --lower-view full --screenshot assets/03-sobu-full-route.png` |
| `04-tokyo-transfer-info.png` | Tokyo transfer panel (JO19) | `uv run preview_display.py --route audio/sobu/1217F/route.json --stop 0 --lower-view transfer --screenshot assets/04-tokyo-transfer-info.png` |
| `05-shinjuku-transfer-info.png` | Shinjuku transfer panel (JY17) | `uv run preview_display.py --route audio/yamanote/1208G/route.json --stop 22 --lower-view transfer --screenshot assets/05-shinjuku-transfer-info.png` |
| `06-setup-screen.png` | Setup screen — the CLASSIC flow, **retired 2026-07-30** along with `preview_chrome.py`. Historical image only; the shipped flow is TIMS (08/09) | not regenerable |
| `07-yamanote-5station-tokyo.png` | E235-0 Yamanote 5-station zoomed view at Tokyo (transfer-dense cluster: 新橋/有楽町/東京/神田/秋葉原) | `uv run preview_display.py --route audio/yamanote/1208G/route.json --stop 6 --model e235_0 --lower-view eight --mode kanji --screenshot assets/07-yamanote-5station-tokyo.png` |
| `08-tims-pa-setting.png` | TIMS PA-setting page (C07AA) in the READY state — route committed, launch cluster armed | `uv run _dev_scripts/gen_readme_tims_pages.py` |
| `09-tims-diagram-select.png` | TIMS diagram-choice page (C07AF) — 中央線快速 run-pattern table | `uv run _dev_scripts/gen_readme_tims_pages.py` |

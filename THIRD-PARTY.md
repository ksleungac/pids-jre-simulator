# Third-Party Material

This repository contains material that is not covered by the MIT license in
[LICENSE](LICENSE). That license applies to the source code and documentation
authored for this project; everything listed below belongs to its respective rights
holder and is not licensed by this project.

Read this before redistributing any part of this repository.

---

## Covered by the MIT license

- Python source at the project root and under `displays/`, `auto_input/`, `tims/`,
  `_tests/`, `_dev_scripts/`, `_harness/`
- Documentation (`*.md`) and `.claude/`
- Route and translation data: `data/*.json`, `audio/**/route.json`
- Project-authored artwork: `data/e235_0/five_station_band.png`,
  `data/train_icons/`, `docs/assets/roadmap.*`
- Packaging (`pyproject.toml`, `uv.lock`)

## Transit operator marks and logos

`data/line_icons/`, `_references/lcd/line_badges/`

Line symbols and operator logos for JR East, Tokyo Metro, Toei Subway, Rinkai Line,
Tokyo Monorail, Nippori-Toneri Liner and Tokyo Sakura Tram, sourced from
[Wikimedia Commons, Category:Rapid transit icons of Japan](https://commons.wikimedia.org/wiki/Category:Rapid_transit_icons_of_Japan).

**Public domain (34 files).** Tagged `PD-textlogo` on Commons: the marks consist only
of simple geometric shapes or text and do not meet the threshold of originality
required for copyright protection.

**CC BY-SA 4.0 (3 files).** Licensed under
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0).
Each has been converted to PNG and resized for display in this application;
the adapted versions remain under the same license.

| File | Author | Adapted as |
|---|---|---|
| `Shinkansen_jre.svg` | Original: Unknown. Vector: Carnby and Perhelion | `data/line_icons/shinkansen_jr_east.png` |
| `Shinkansen_jrc.svg` | KANAO22 | `data/line_icons/shinkansen_jr_central.png` |
| `Tokyo_Sakura_Tram_symbol.svg` | 東京都交通局 (Tokyo Metropolitan Bureau of Transportation) | `data/line_icons/sakura_tram.png` |

**Trademarks.** Public-domain copyright status does not affect trademark rights. These
marks are registered trademarks of their respective operators and are reproduced here
to identify the rail lines they designate. This project is not affiliated with,
endorsed by, or sponsored by East Japan Railway Company, Tokyo Metro, the Tokyo
Metropolitan Bureau of Transportation, or any other operator.

## Audio recordings

`audio/**/*.mp3`

Station announcements and departure melodies from the Japanese rail network. Copyright
in these recordings and in the melodies they contain is held by East Japan Railway
Company and the respective melody rights holders. They are included for use with this
simulator and are not licensed for redistribution by this project.

**Recordists.** The audio was captured at the platform and published by individual
railway enthusiasts, and this project cut its files from those publications. Crediting
them below does not make them rights holders and does not grant this project any
licence — the copyright position above is unchanged. It records who did the work.

Sources are recorded as the work happens wherever that step was in place. Two bodies of
audio qualify, both mapped file-by-file in `audio/README.md`:

- **Utsunomiya Line** (`audio/utsunomiya/`) — 29 source recordings,
  [§ "JU — Utsunomiya sources"](audio/README.md).
- **Chūō Line `602H`** (9 of `audio/chuo/`'s 62 PA files) — two recordings, both by
  **East Railway Redwing**, [§ "JC — Chuo sources"](audio/README.md). The line's other
  53 files predate the step. One of the nine, `shinjuku-arr-602H`, is **constructed**
  rather than captured: five pieces, three from `stu9Duc6X8I` and two from the pool's own
  `shinjuku-arr-916H` — whose own source is among the 53 that predate this step and is
  therefore uncredited. Documented at that section.

The Utsunomiya recordings come from:

| Recordist | Recordings |
|---|---|
| 全国駅メロチャンネル | 9 |
| ちいぼす | 7 |
| East Railway Redwing | 1 — the single run all 46 of `1545E`'s announcement files were cut from |
| µ'wing | 1 — the single run all 45 of `3520M`'s announcement files were cut from |
| 70-000 SHINANO · Kent_K · SAGAMI-LINE さがみせん · Ueno-Tokyo Line · ケヨポコ チャンネル short · ハマ音鉄 · 下今市 · 京葉ラビット · 武蔵野快速 · 関石ライン / Kamishi Line · 音鉄DK | 1 each |

Sources for the other lines were not recorded at the time and cannot now be recovered
reliably. Their recordists are uncredited here for that reason, not because no one is
owed the credit.

**If you are one of these recordists** and would prefer your work not be used here, or
would prefer to be credited differently, open an issue and it will be removed or
corrected.

µ'wing asks that non-personal use of their recordings be registered through a form linked
from the video description, personal-scope use being exempt. This repository was submitted
to them on 2026-08-21; the material comes out if they would rather it did not stand.

## Fonts

`fonts/`

- **Noto Sans** (`NotoSans*.otf`) — SIL Open Font License 1.1. License text is
  included as `fonts/NotoSans-OFL.txt`.
- **All other faces** are commercial font software owned by their respective foundries.
  They are not covered by the MIT license and are not licensed for redistribution by
  this project.
- **ShinGoPr6N** (Morisawa) is **not** in this repository and is not distributed with
  the release. The LCD renders it from a pre-rendered raster atlas, so neither the
  shipped build nor a clone contains the font software. Regenerating that atlas from
  source requires a licensed copy of the faces, which you must obtain yourself.

## Assets derived from third-party software

`ocr_templates/`, `data/disclaimer/`

Glyph templates and reference frames extracted from a third-party train simulator's
on-screen display, used to locate and read its HUD. Rights in the depicted software
and its interface belong to its publisher and to East Japan Railway Company.

The release also contains `font_atlas/`, pre-rendered raster output of the LCD
typefaces. It is generated at build time and is not in this repository. See § Fonts.

## Reference material

`_references/lcd/`, `_references/tims/`, `_references/bell/`, `docs/assets/*.png`

Photographs of in-service train displays, cab consoles and station platform equipment,
collected to calibrate the renderer, and screenshots of this application in operation.
The displays, equipment and interface designs depicted are the property of East Japan
Railway Company.

---

## If you fork this

The code is yours to use under the MIT license. The material above is not — obtain your
own rights, substitute your own assets, or omit them. A fork that redistributes this
repository wholesale inherits every obligation and risk listed here, and the MIT grant
does not cover any of it.

When adding a new asset class to this repository, add it to this file in the same
change.

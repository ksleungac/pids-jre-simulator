# JRE-PA-Simulator

Japanese Train PA (Public Address) Simulator — JR East style train announcements with visual LCD display.

**[繁體中文](README.zh-HK.md)** · **[简体中文](README.zh-CN.md)** · **[Supported Routes](ROUTES.md)**

---

## Screenshots

| Compact view | Skip animation | Full-route view |
|---|---|---|
| ![](assets/01-keihin-tohoku-compact.png) | ![](assets/02-sobu-skip-animation.png) | ![](assets/03-sobu-full-route.png) |

| Transfer info (Tokyo) | Transfer info (Shinjuku) | Setup screen |
|---|---|---|
| ![](assets/04-tokyo-transfer-info.png) | ![](assets/05-shinjuku-transfer-info.png) | ![](assets/06-setup-screen.png) |

---

## Download

From [**Releases**](https://github.com/ksleungac/pids-jre-simulator/releases/latest):

- **`JRE-PA-Simulator-<version>-distribution.zip`** — full bundle (exe + fonts + data + audio, ~629 MB). Extract and run `JRE-PA-Simulator.exe`.
- **`JRE-PA-Simulator.exe`** — standalone exe, if you already have `fonts/`, `data/`, and `audio/` locally.

---

## Usage

Pick a line and diagram on the setup screen, press Enter to start.

**Page Down drives everything.** The simulation is fully manual — the train doesn't advance on a timer; every announcement and every stop happens only when you press Page Down.

| Key | Action |
|-----|--------|
| Page Down | Next PA announcement / advance to next stop |
| Page Up | Play departure melody (press again to skip to closing-door announcement) |
| End | Pause |
| ESC | Quit |

A **yellow square** on the display means this stop has more than one announcement — keep pressing Page Down to play them all before arriving at the station.

The upper LCD cycles between Japanese, Furigana, and English. Major JR East interchange stations also show their 3-letter Roman code (AKB, TYO, SJK…) above the line-code square.

---

## Planned Features

- More route diagrams
- Additional LCD styles (E233-0, E231, …)
- Enhanced Lower LCD

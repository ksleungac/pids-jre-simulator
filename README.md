# JRE-PA-Simulator

Japanese Train PA (Public Address) Simulator - JR East style train announcements with visual LCD display.

---

## Installation / 安装

```
your-folder/
├── JRE-PA-Simulator.exe/
│── fonts/
│── data/
└── audio/
```

### 中文

1. **下载** [Releases](https://github.com/ksleungac/pids-jre-simulator/releases) 中的 `JRE-PA-Simulator.exe`以及整个repo，把exe放在repo根目录底下
2. **安装字体** 安装全部字体

#### audio和data文件夹中的数据不定时更新。如果需要最新的路线数据，请克隆此代码库并且定期从master中git pull。
---

## Usage / 使用方法

| Key / 按键 | Action / 功能 |
|------------|--------------|
| Page Down | Next PA announcement (下条广播) |
| Page Up | Departure Melody / 发车音乐（音乐播放中的时候按第二下跳到音乐结束，关门播报） |
| End | Pause / 暂停 |
| ESC | Quit / 退出 |

---

## Supported Routes / 対応路線 / 対応路線

| 路線 (Line) | Diagram | 列車種別 (Train Type) |
|-------------|-------------------|----------------------|
| 山手線 | 1275A | 内回り |
| 埼京線 | 759K | 各駅停車 |
| 埼京線・川越線 | 1349F | 快速 |
| 京浜東北・根岸線 | 1275A | 各駅停車 |
| 京浜東北・根岸線 | 727B | 快速 |
| 南武線 | 603F | 各駅停車 |
| 南武線 | 4027F | 快速 |
| 上野東京ライン・常磐線直通 | （なし） | 快速 |
| 中央線快速 | 916H | 中央特快 |
| 中央線快速 | 1654T | 快速 |
| 京葉線 | 780Y_1510Y | 普通 |
| 東海道線 | 1865E | 普通 |
| 東海道線 | 3535E | 快速アクティー |

---

## Planned Features / 计划功能

- **More route diagrams** - Additional train variations (更多列车种类)
- **Additional LCD styles** - E233-0 番台，E231 series, etc. (更多 LCD 样式)
- **Enhanced Lower LCD** - More features and information display (下部 LCD 更多功能)

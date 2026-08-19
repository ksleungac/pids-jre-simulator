# JRE-PA-Simulator

JR 东日本风格列车广播与车内 LCD 显示模拟器。

**[English](../README.md)** · **[繁體中文](README.zh-HK.md)** · **[支持的路线](ROUTES.md)**

---

## 截图

| 精简显示 | 通过站动画 | 全路线显示 |
|---|---|---|
| ![](assets/01-keihin-tohoku-compact.png) | ![](assets/02-sobu-skip-animation.png) | ![](assets/03-sobu-full-route.png) |

| 换乘信息 (东京) | 换乘信息 (新宿) | 山手线 5 站显示 (E235-0) |
|---|---|---|
| ![](assets/04-tokyo-transfer-info.png) | ![](assets/05-shinjuku-transfer-info.png) | ![](assets/07-yamanote-5station-tokyo.png) |

| 报站设置 | 车次选择 |
|---|---|
| ![](assets/08-tims-pa-setting.png) | ![](assets/09-tims-diagram-select.png) |

---

## 下载

前往 [**Releases**](https://github.com/ksleungac/pids-jre-simulator/releases/latest):

- **`JRE-PA-Simulator-<version>-distribution.zip`** — 完整版本(包含 exe、字体、数据和音频文件,约 629 MB)。解压后运行 `JRE-PA-Simulator.exe`。
- **`JRE-PA-Simulator.exe`** — 独立可执行文件,如你已经拥有 `fonts/`、`data/` 和 `audio/` 文件夹。

---

## 使用方法

在选择界面选择路线和车次,按 Enter 开始。

**自动或手动操作。** 程序可以读取游戏画面上的信息,在适当的时候播放每一段广播 — 在报站设置页按 **OCR自动报站启动**,之后专心驾驶即可。需要游戏在主显示器上运行,分辨率也要在支持范围内。大部分用户都是这样用。

**手动操作时,所有操作通过 Page Down**。程序不会自动跳到下一站 — 播放广播、切换到下一站都需要手动按 Page Down。

| 按键 | 功能 |
|------|------|
| Page Down | 下一段广播／前往下一站 |
| Page Up | 播放发车音乐(播放途中再按一次可跳至关门广播) |
| End | 暂停 |
| ESC | 退出 |

画面上出现**黄色方块**表示该站有多段广播 — 请在到站之前按 Page Down 播完所有广播。

顶部 LCD 会循环切换日文、假名、英文显示。主要 JR 东日本换乘站也会在线路代码方块上方,显示 3 个字母的车站代码(AKB、TYO、SJK…)。

---

## 计划中的功能

- 更多线路及车次
- 更多 LCD 样式(E233-0 番台、E231 系列等)
- 强化下部 LCD
- 支持更多屏幕尺寸及画面比例

---

## 鸣谢

线路及运营商标志均取自 [Wikimedia Commons](https://commons.wikimedia.org/wiki/Category:Rapid_transit_icons_of_Japan)，感谢绘制及维护这些图标的贡献者，其中新干线与东京樱花电车标志来自 Carnby、Perhelion、KANAO22 及东京都交通局。

完整鸣谢及素材资料：[THIRD-PARTY.md](../THIRD-PARTY.md)。

# v0.7.0 release images

Screenshots for the v0.7.0 release notes, referenced by tag-pinned raw URLs. Separate from the
README screenshots in `docs/assets/`. Every `preview_display.py` render below is
`uv run preview_display.py <flags> --screenshot docs/assets/v0.7.0/<file>`.

| File | Shows | How to regenerate |
|---|---|---|
| `01-e233-full-route-takao.png` | E233-0 full route at 高尾 | `--route chuo/1654T --model e233_0 --stop 0 --pa 2 --lower-view full` |
| `02-e233-6station-ochanomizu.png` | six-station view, 次は御茶ノ水 | `--route chuo/1654T --model e233_0 --stop 29 --pa 0 --lower-view eight` |
| `03-e233-transfer-shinjuku.png` | transfer view at 新宿 | `--route chuo/1654T --model e233_0 --stop 21 --pa 2 --lower-view transfer` |
| `04-e233-patterns-overview.png` | patterns overview at 高尾 | `--route chuo/1654T --model e233_0 --stop 0 --pa 2 --lower-view overview` |
| `05-e233-priority-seats.png` | priority-seat placard | `--route chuo/1654T --model e233_0 --stop 21 --pa 2 --lower-view priority` |
| `08-e233-terminus-tokyo.png` | まもなく終点 東京 | `--route chuo/602H --model e233_0 --stop 26 --pa 0 --lower-view full` |
| `09-e233-keihin-shinagawa.png` | E233-0 on Keihin-Tōhoku | `--route keihin/1275A --model e233_0 --stop 26 --pa 0 --lower-view full` |
| `10-e233-saikyo-shinjuku.png` | E233-0 on Saikyō, six stations at 新宿 | `--route saikyo/1349F --model e233_0 --stop 3 --pa 0 --lower-view eight` |
| `11-e233-utsunomiya.png` | E233-0 on Utsunomiya | `--route utsunomiya/3520M --model e233_0 --stop 10 --pa 0 --lower-view full` |
| `12-utsunomiya-3520M-kuroiso.png` | 3520M 快速ラビット at 黒磯 | `--route utsunomiya/3520M --stop 0 --pa 2 --lower-view full` |
| `13-utsunomiya-1545E-ueno.png` | 1545E 普通 熱海ゆき, approaching 上野 | `--route utsunomiya/1545E --stop 22 --pa 0 --lower-view full` |
| `14-bell-box.png` | the bell box, ringing, beside the main window at 新宿 | a composite: `--route chuo/1654T --model e233_0 --stop 21 --pa 2 --lower-view full`, and `uv run _dev_scripts/preview_bell.py --state ringing --zoom 1` cropped above its label, placed 14px to the right on the bell preview's own background |
| `15-remote-ipad.jpg` | the app mirrored to an iPad beside the game | the author's photograph; not regenerable |
| `16-chuo-602H-tachikawa.png` | 602H 通勤特快 at 立川, with the 青梅線 leg | `--route chuo/602H --model e233_0 --stop 0 --pa 2 --lower-view full` |
| `18-tims-remote-setting.png` | TIMS 設定, remote control on LAN, in English | `_dev_scripts/preview_setup_tims.py --screen stream` with `stream_setting.ACTIVE_LANG` and `tims.band.ACTIVE_LANG` set to `"en"` before `main()`, and the saved `stream_mode` on LAN |

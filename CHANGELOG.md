# 更新日志

## v1.2.2

- **新增大写锁定指示灯**：顶部状态栏、连接图标左侧，实心圆灯 + `A` 表示大写，空心圆灯 + `a` 表示小写，颜色跟随主题。
  - 新增第 6 个绘制区域 `ui_geo[5]`（13×9 @ 214,14），掩码总量 1378 → 1393 字节；`tools/assets.py` 用 `MASK_TOTAL` 校验。
  - 屏内在 `rainy_hook_native_key` 里对 usage `57`（CapsLock）翻转本地标志，`OP 11 / ID 16` 可只读查询状态。
  - 主控不转发大写状态，所以上电后第一次按 CapsLock 之前显示默认「空心 + a」。
- **GIF 报错更具体**：直接把实际尺寸、体积和下一步动作写在提示里（例如「GIF 尺寸是 480×270，必须严格 320×172…请用主题定制台」），不再统一报「请选择 320×172」。
- 显示诊断页新增「大写锁定」只读字段；网页工作台与定制台预览同步画上大写灯。

## v1.2.1

修「第一步预检失败：主控基线不是官方 0.64，拒绝刷写」。

- `inputs/main-stock.bin` 换成**官方 0.64** 主控镜像（284,492 B，SHA `31a9eb80…`），旧的 0x3F 镜像改名 `inputs/main-stock-063beta1.bin` 单独保留。
- 内置快照按 0.64 重新编译：主控 `main.bin` SHA `2dcba755…`，`stockVersion` = `0.64`，`stockSha256` = `31a9eb80…`；屏幕 `ips.bin` 不变（`4df17216…`）。
- `tools/extract_stock.py` 按基线自动命名解出的主控镜像，重新解 vendor HTML（0x3F）不会覆盖 0.64 的 `main-stock.bin`。
- `docs/build.md`、`inputs/README.md`、README 补上「向导只接受 0.64」的原因与两套基线的正确用法。

## v1.2.0

这一版把「固件包」加回软件与仓库，同时彻底删掉歌词播放器扩展。

### 自带固件包（开箱即刷）

- 仓库重新收入 `vendor/`（原厂离线烧录网页）、`inputs/`（`ips-stock.bin`、`main-stock.bin`、`libISP585.a`）与 `toolbox/firmware/`（内置固件快照）。
- exe 默认打包 `inputs/`、`build/`、`toolbox/firmware/` 与 clang：双击即可 ①→⑥ 直接刷，无需再导入 `ips-stock.bin`，也无需自行安装编译器。
- 内置快照版本：主控 `V7.1`（`0x3F` beta1 基线，294,912 B）+ 屏幕 `L6 / UI 0.6.3`（507,904 B）+ 樱花粉 S1 动画（8 帧 / 16,434 B / 71 包）。
- 定制台「应用并重新编译」仍然可用，改完主题后 `python toolbox/snapshot.py` 可把新固件冻结成快照。
- 仍保留 `python toolbox/make_exe.py --compliant` 打包「不含原厂固件」的分发版。

### 移除歌词播放器扩展

- 删除 `firmware/ips-lyrics/`、`desktop/`（Windows 后台与控制台）、`tools/fontpack.py`、`web/font.mjs`、`docs/lyrics.md`、字库相关测试与 `assets/player-*.png`、`assets/lyrics-console.png`。
- 网页工作台去掉「03 / OPTIONAL LYRICS」区块（字库上传 / 替换 / 删除），固件校验会明确拒绝带 `variant` 的旧歌词版清单。
- 定制台去掉 `lyricsBorder` / `lyricsPanel` 两个配色字段，构建脚本去掉 `--lyrics` / `--font` 参数。
- `package.json` 只保留协议与前端测试脚本，不再依赖 `node-hid`。

### 文档

- README、`docs/` 全面改成单形态（基础屏幕版 + 桌面工具箱）叙述，新增「自带固件包」与「从歌词版退回基础版」的操作说明。
- `AGENTS.md`、`DISCLAIMER.md`、`THIRD_PARTY_NOTICES.md` 更新分发边界：`vendor/`、`inputs/`、`toolbox/firmware/` 随仓库分发但**非 MIT**。

## 0.2.0-alpha.4（上游历史）

按 A 基础屏幕 / B 传统歌词 / C 沉浸与音量区分功能和升级依赖（本分支已移除 B、C）。

## 0.2.0-alpha.3（上游历史）

- 增加官方 0.64 精确 SHA 与独立主控地址表，保留旧 0x3F 基线，不混用 USB、RTC 和 RAM worker 地址。
- 官方 0.64 主控与屏幕配置已有单台设备烧录校验及短时校时读回。

## 0.2.0-alpha.2 / alpha.1（上游历史）

- 拆分基础屏幕版与可选歌词扩展；屏幕补丁新增只读芯片容量与系列查询（UI `0.6.3` / 协议 `L6`）。

## 0.1.0-alpha.1（上游历史）

- 首次发布基础像素屏补丁（大单键、时钟、电量、模式图标与三套原创几何机器人主题）。

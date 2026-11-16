# 更新日志

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

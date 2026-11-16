# 第三方资源与许可说明

## 1. 自有内容（MIT License）

根目录 [LICENSE](LICENSE) 中的 MIT 协议及原作者署名**只覆盖以下**由本项目独立编写或绘制的内容（**不包含 `vendor/` 目录下的原厂随仓文件**）：

- 所有固件 C 语言补丁源码、链接脚本与构建工具（`firmware/`、`tools/`）；
- 桌面歌词后台与本地网页工作台（`desktop/`、`web/`）；
- 自动化测试与全部说明文档（`tests/`、`docs/`、根目录 `.md`）；
- `profiles/font.json`、`profiles/keys.json`、`profiles/themes.json` 中的像素点阵与配色配置；
- `tools/assets.py` 几何生成的默认像素机器人图标、GIF 动画及预览图。

## 2. 歌词字库（SIL OFL-1.1）

如果你启用了可选的歌词播放器扩展，使用 `tools/fontpack.py` 从本地 **Noto Sans CJK SC** 生成 `FONT.BIN`（Rainy Lyrics Pixel 20）时：

- 源字体版权归属：© 2014–2021 Adobe (<http://www.adobe.com/>)，上游仓库为 [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)。
- 生成的 `FONT.BIN` 属于字体衍生作品，继续受 [SIL OFL-1.1](licenses/OFL-1.1.txt) 约束（注意保留版权声明、不得单独售卖字体文件、衍生版本同样沿用 OFL-1.1）。生成工具会自动在输出目录附带 `OFL-1.1.txt` 和 `FONT-NOTICE.txt`。
- 本仓库不直接打包源 `.otf` 字体或现成的 `FONT.BIN`。

## 3. 网易云 Elog 解析适配（上游 MIT）

`desktop/netease-timeline.cjs` 中关于网易云音乐本地日志的字节映射与事件结构参考了以下两个 MIT 开源项目，并在 [licenses/netease-elog-MIT.txt](licenses/netease-elog-MIT.txt) 中保留了完整的上游版权声明：

- [Coooookies/netease-cloudmusic-detector](https://github.com/Coooookies/netease-cloudmusic-detector) — Copyright (c) 2025 ButterCookies
- [344272586-sketch/dsh-pet-qqmusic](https://github.com/344272586-sketch/dsh-pet-qqmusic/blob/main/THIRD_PARTY_NOTICES.md) — Copyright (c) 2026 YouRan；Copyright (c) 2026 dsh-pet-qqmusic contributors

另外，QQ 音乐 / 网易云音乐的歌曲名、歌词文本及相关网络接口权利归各自平台及版权方所有。

## 4. 随仓附带的非 MIT 原厂文件

为了方便玩家核对匹配版本、本地一键提取 `inputs/` 构建原料，以及在需要时直接刷回出厂固件，仓库在 [vendor/](vendor/README.md) 中附带了一份原厂离线烧录网页（具体用途见该目录说明）：

- [vendor/Rainy75V2烧录工具20261112-1beta1.html](vendor/Rainy75V2烧录工具20261112-1beta1.html)：网页版 v1.1（打包日期 `2026-11-12`），内嵌三份以 Base64 + 异或混淆保存的 WOB 原厂固件二进制：
  - **键盘主控（`kbd`）**：版本 `0x3F`（`appPid 0x3075` / `iapPid 0x3079`）
  - **2.4G 接收器（`rcv`）**：版本 `0x26`（`appPid 0x3071` / `iapPid 0x3070`，本项目补丁不会提取或修改接收器）
  - **IPS 屏幕（`ips`）**：版本 `0x0002`（`appPid 0x3075` / `iapPid 0x3078`）

**版权与开源边界说明**：上述内嵌的原厂固件二进制归 WOB 原厂及相关芯片权利人所有，**并没有因为放入本仓库而转为 MIT 开源**。如果你只需要提取源码部分做纯开源二次分发，或应权利人要求调整分发范围，可直接移除整个 `vendor/` 目录，其余目录不受影响。

## 5. 仓库仍不包含的文件

以下第三方、编译产物或私人内容**不随本仓库分发**，也没有被转为 MIT 开源：

- WCH CH585 官方 SDK 源码与 `libISP585.a` 静态库（本地构建产物中链接进的该部分内容仍受原 SDK 许可限制，不能当成纯 MIT 固件随意分发）；
- 从 `vendor/` 解出的 `.bin`、本地编译合并后的完整固件（`build/`，因同时包含原厂镜像与 `libISP585.a`）；
- `NotoSansCJKsc-Regular.otf` 原字体、打包后的 `FONT.BIN`，以及个人角色贴图、私人设备备份或个人媒体日志。

## 6. 开发与运行依赖

| 依赖 | 用途 | 备注 |
| --- | --- | --- |
| Python 3.10+ | 构建脚本、字体打包、本地 HTTP 服务 | Python 自身许可 |
| Pillow | 生成机器人 GIF 与效果预览图 | HPND 许可 |
| fontTools | 读取源字体 cmap 与元数据 | MIT 许可 |
| LLVM / Clang / LLD | 交叉编译 ARM Cortex-M4 与 RISC-V 固件 | Apache-2.0 WITH LLVM-exception |
| Node.js 22+ | 运行单元测试及可选 Windows 歌词后台 | Node.js 自身许可 |
| `node-hid` 3.4.0 | 歌词后台访问键盘 USB HID | MIT 及对应原生库许可 |
| Playwright（可选） | 跑网页界面自动化烟雾测试 | Apache-2.0 |
| Unicorn（可选） | 本地模拟运行 ARM 固件指令 | GPL-2.0（仅本地开发测试用，不打包） |

相关芯片与官方资料入口：
- [WCH CH585 官方 SDK](https://github.com/openwch/ch585)（兼容 `libISP585.a` 来自 commit `db889195f07b8f3f4e7bf2c55f96a35daa14bebf`）
- [雅特力 AT32F435 产品页](https://www.arterytek.com/en/product/AT32F435.jsp)
- [WOB 官方网页驱动](https://wobwxe.com/)

## 5. 本分支（Rainy75 V2 桌面工具箱）的分发边界

本仓库是在 [xixiaotiam1219-lab/rainy75v2-tft](https://github.com/xixiaotiam1219-lab/rainy75v2-tft)（MIT，© 2026 xixiaotiam1219-lab）基础上的二次开发分支，新增部分代码同样以 MIT 发布（版权归属见 [NOTICE](NOTICE)）。

为遵守第三方权利，本分支**明确不再分发**以下内容（上游仓库里可能存在，这里一律移除）：

| 内容 | 原因 | 用户如何获得 |
| --- | --- | --- |
| `vendor/`（原厂离线烧录网页，内嵌 WOB 原厂固件） | 固件二进制版权归 WOB 及相关权利人，不属于 MIT | 从 WOB 官方渠道获取 |
| `inputs/`（`ips-stock.bin`、`main-stock.bin`、`libISP585.a`、字体等编译原料） | 同上；`libISP585.a` 属 WCH SDK | 从自己的设备备份或官方 SDK 获取 |
| `toolbox/firmware/`（内置固件快照） | 由原厂固件派生 | 本地用 `python toolbox/snapshot.py` 自行生成 |
| `build/`（编译产物 `.bin`） | 同上 | 本地编译生成 |
| LLVM / clang 工具链 | 第三方编译器，体积大且需单独附带许可证 | 自行安装 `winget install LLVM.LLVM` |

因此 Release 中的 `Rainy75Toolbox-lite.exe` 不含任何原厂固件与编译器：首次使用时由用户在「主题定制台 → ⓪」导入自己的 `ips-stock.bin`，或在刷机向导里选择本机的 `.bin` 文件。这些文件只留在本机，不会被上传。

> 上游 README 与 `docs/` 中提到的 `vendor/`、`inputs/` 步骤仍然适用，只是相关文件需要你自行准备。若你需要完整的「开箱即刷」体验，请在上游仓库基础上本地打包（`python toolbox/make_exe.py`）。

### 5.1 示例角色 / 动画素材

本仓库**不附带任何来源不明的角色 GIF 或动画素材**。公开发布的 exe 也**不包含**作者本机上传的角色动画，
首次使用需要你自己上传 GIF（`assets/` 下三张 `robot-*.gif` 是本项目几何绘制的原创素材，可按 MIT 使用）。

如果你在自己的副本里手滑放进了来自网络的图片/动画，请自行确认其授权；作者不为此类第三方素材主张任何权利，
收到权利人通知后会立即移除。仓库与 release 中不包含这类内容。

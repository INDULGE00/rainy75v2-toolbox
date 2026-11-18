# 第三方资源与许可说明

## 1. 自有内容（MIT License）

根目录 [LICENSE](LICENSE) 中的 MIT 协议及原作者署名**只覆盖以下**由本项目独立编写或绘制的内容（**不包含 `vendor/` 目录下的原厂随仓文件**）：

- 所有固件 C 语言补丁源码、链接脚本与构建工具（`firmware/`、`tools/`）；
- 本地网页工作台与离线桌面工具箱（`web/`、`studio/`、`toolbox/`）；
- 自动化测试与全部说明文档（`tests/`、`docs/`、根目录 `.md`）；
- `profiles/font.json`、`profiles/keys.json`、`profiles/themes.json` 中的像素点阵与配色配置；
- `tools/assets.py` 几何生成的默认像素机器人图标、GIF 动画及预览图。

## 2. 随仓附带的非 MIT 原厂文件

为了方便玩家核对匹配版本、本地一键提取 `inputs/` 构建原料，以及在需要时直接刷回出厂固件，仓库在 [vendor/](vendor/README.md) 中附带了一份原厂离线烧录网页（具体用途见该目录说明）：

- [vendor/Rainy75V2烧录工具20261112-1beta1.html](vendor/Rainy75V2烧录工具20261112-1beta1.html)：网页版 v1.1（打包日期 `2026-11-12`），内嵌三份以 Base64 + 异或混淆保存的 WOB 原厂固件二进制：
  - **键盘主控（`kbd`）**：版本 `0x3F`（`appPid 0x3075` / `iapPid 0x3079`）
  - **2.4G 接收器（`rcv`）**：版本 `0x26`（`appPid 0x3071` / `iapPid 0x3070`，本项目补丁不会提取或修改接收器）
  - **IPS 屏幕（`ips`）**：版本 `0x0002`（`appPid 0x3075` / `iapPid 0x3078`）

**版权与开源边界说明**：上述内嵌的原厂固件二进制归 WOB 原厂及相关芯片权利人所有，**并没有因为放入本仓库而转为 MIT 开源**。如果你只需要提取源码部分做纯开源二次分发，或应权利人要求调整分发范围，可直接移除整个 `vendor/` 目录，其余目录不受影响。

## 3. 仓库仍不包含的文件

以下第三方、编译产物或私人内容**不随本仓库分发**，也没有被转为 MIT 开源：

- WCH CH585 官方 SDK 源码与 `libISP585.a` 静态库（本地构建产物中链接进的该部分内容仍受原 SDK 许可限制，不能当成纯 MIT 固件随意分发）；
- 从 `vendor/` 解出的 `.bin`、本地编译合并后的完整固件（`build/`，因同时包含原厂镜像与 `libISP585.a`）；
- 个人角色贴图、私人设备备份或个人媒体日志。

## 4. 开发与运行依赖

| 依赖 | 用途 | 备注 |
| --- | --- | --- |
| Python 3.10+ | 构建脚本、装备素材生成、本地 HTTP 服务 | Python 自身许可 |
| Pillow | 生成机器人 GIF 与效果预览图 | HPND 许可 |
| LLVM / Clang / LLD | 交叉编译 ARM Cortex-M4 与 RISC-V 固件 | Apache-2.0 WITH LLVM-exception |
| Node.js 22+ | 运行协议与前端单元测试 | Node.js 自身许可 |
| Playwright（可选） | 跑网页界面自动化烟雾测试 | Apache-2.0 |
| Unicorn（可选） | 本地模拟运行 ARM 固件指令 | GPL-2.0（仅本地开发测试用，不打包） |

相关芯片与官方资料入口：
- [WCH CH585 官方 SDK](https://github.com/openwch/ch585)（兼容 `libISP585.a` 来自 commit `db889195f07b8f3f4e7bf2c55f96a35daa14bebf`）
- [雅特力 AT32F435 产品页](https://www.arterytek.com/en/product/AT32F435.jsp)
- [WOB 官方网页驱动](https://wobwxe.com/)

## 5. 本分支（Rainy75 V2 桌面工具箱）的分发边界

本仓库是在 [xixiaotiam1219-lab/rainy75v2-tft](https://github.com/xixiaotiam1219-lab/rainy75v2-tft)（MIT，© 2026 xixiaotiam1219-lab）基础上的二次开发分支，新增部分代码同样以 MIT 发布（版权归属见 [NOTICE](NOTICE)）。

从 `v1.2.0` 起本分支重新**随仓库附带固件包**，这样 exe 与源码都能开箱即刷。附带范围与权利归属：

| 内容 | 说明 | 许可 |
| --- | --- | --- |
| `vendor/Rainy75V2烧录工具20261112-1beta1.html` | 原厂离线烧录网页，内嵌键盘 `0x3F` / 接收器 `0x26` / 屏幕 `0x0002` 三份原厂固件 | 归 WOB 原厂所有，**非 MIT** |
| `inputs/ips-stock.bin`、`inputs/main-stock.bin` | 由上面的网页解出的原厂编译输入，`build.py` 会核对 SHA-256 | 同上，**非 MIT** |
| `inputs/libISP585.a` | WCH CH585 官方 SDK 的 Flash 读写静态库 | 归 WCH 所有，**非 MIT** |
| `toolbox/firmware/` | 内置固件快照（主控 + 屏幕补丁固件 + S1 动画 + info.json） | 含原厂代码派生内容，**非 MIT** |
| `build/`、`llvm/` | 本地编译产物与 LLVM 工具链 | 不随仓库分发 |

**所以请分清两种授权**：根目录 MIT 只覆盖自有源码、文档与几何绘制的机器人素材；上表内容仅供你在本机生成并刷入自己的键盘，**不要把它们单独打包再分发**，也不要改掉署名后重新标为 MIT。

如果权利人要求调整分发范围，可以直接删除 `vendor/`、`inputs/`、`toolbox/firmware/` 三个目录，再按 `toolbox/README.md` 用 `--compliant` 打包 exe，其余目录不受影响。

### 5.1 示例角色 / 动画素材

本仓库**不附带任何来源不明的角色 GIF 或动画素材**。`assets/` 下三张 `robot-*.gif` 是本项目几何绘制的原创素材，可按 MIT 使用；exe 内置快照里的 S1 动画也由 `tools/assets.py` 生成。

如果你在自己的副本里手滑放进了来自网络的图片/动画，请自行确认其授权；作者不为此类第三方素材主张任何权利，收到权利人通知后会立即移除。

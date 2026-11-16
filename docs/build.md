# 本地构建指南

因为刷机所需的完整 `.bin` 要把 WOB 原厂镜像、芯片厂静态库 `libISP585.a` 和本仓库的开源补丁拼在一起，所以最终固件仍需要你在自己电脑上编译生成（完整步骤很短，装好工具跑几条命令就行）。其中对应的原厂烧录网页已经放在仓库的 [vendor/](../vendor/README.md) 目录里（内含原厂二进制，**非 MIT 开源**），你可以直接从里面一键解出主控和屏幕固件；`libISP585.a` 则需从 WCH 官方开源仓库下载放到 `inputs/`。

---

## 第一步：安装基础工具

1. **Python 3.10+**（推荐 3.12）
   安装项目依赖（包含生成机器人 GIF 所需的 Pillow）：
   ```sh
   python -m pip install -r requirements-dev.txt
   ```

2. **LLVM Clang 与 LLD（必须带 ARM 和 RISC-V 后端）**
   因为屏幕芯片是 ARM（AT32F435），键盘主控是 RISC-V（CH585），所以需要一套同时支持这两种架构的 Clang + LLD。
   - **Windows 推荐装法**：直接从 [LLVM GitHub Releases](https://github.com/llvm/llvm-project/releases) 下载安装 `LLVM-*-win64.exe`（安装时勾选 `Add LLVM to the system PATH`），或者用命令 `winget install LLVM.LLVM`。
   - 装完重启终端，输入 `clang --version` 和 `lld --version` 确认能正常识别。如果不想加到系统 PATH，后面运行构建脚本时用 `--clang "C:\Program Files\LLVM\bin\clang.exe"` 指定路径也行（路径带空格记得加双引号）。

3. **Node.js 22+（可选）**
   烧录和网页工作台不需要 Node；只有跑自动化测试时才需要安装 [Node.js](https://nodejs.org/) 22 及以上版本。

---

## 第二步：准备 `inputs/` 里的原厂输入文件

构建脚本对原厂输入有严格的 SHA-256 校验，**只支持下面这组匹配版本**（不支持直接跳过校验，因为补丁里的 Hook 地址是针对这个版本算好的）。

### 1. 原厂屏幕与主控固件（`ips-stock.bin`、`main-stock.bin`）

需要的是从应用程序起点开始的 APP `.bin` 镜像（不是带 Bootloader 的整片读写转储）：

| 目标文件名 | 对应原厂版本 | 期望 SHA-256 |
| --- | --- | --- |
| `inputs/ips-stock.bin` | 原厂 IPS `0x0002` | `32defab7902e57eb972a577fc6cbf3a7e57bc772d59b99f11038370412b77f41` |
| `inputs/main-stock.bin` | **官方 0.64 `0x40`（当前默认基线）** | `31a9eb80752c1f8c94951dd6e2e6776eeb216f47ba58919ca36f6e6d26f0e476` |
| `inputs/main-stock-063beta1.bin` | 旧原厂主控 beta1 `0x3F` | `bc575a6d7b19042048705248715a43a67a23c7f217ba0ac464c539a390f4d23b` |

> **刷机向导只接受官方 0.64 基线。** 如果拿 0x3F 编出来的主控固件去刷，预检会直接报
> 「主控基线不是官方 0.64，拒绝刷写」。所以 `inputs/main-stock.bin` 固定放 0.64；旧的
> 0x3F 镜像单独存成 `main-stock-063beta1.bin`，`build.py` 会按 SHA 自动选对应地址表。
> 两种基线**不能混用**同一个 `main-stock.bin` 文件名。

屏幕输入可以直接从仓库随附的原厂离线烧录网页 `vendor/Rainy75V2烧录工具20261112-1beta1.html` 解出（内置键盘 `0x3F`、接收器 `0x26`、屏幕 `0x0002` 三份原厂固件，**版权归原厂所有、不适用 MIT 协议**）。脚本只读文本里内嵌的数据，不会运行网页 JS，也不会提取或改动接收器 `0x26` 固件；解出的主控镜像会按基线自动命名（0x3F → `main-stock-063beta1.bin`，不会覆盖 0.64 的 `main-stock.bin`）：

```sh
python tools/extract_stock.py "vendor/Rainy75V2烧录工具20261112-1beta1.html" --out inputs
```

提取完成后脚本会自动核对 SHA-256，不匹配会直接报错提示；如果你自己手里本来就有同版本官方烧录网页 HTML，也可以把路径换成你自己的文件。

官方 0.64 的主控与屏幕资源要从本地 WOBHub 客户端（`20261113-1`）的 ASAR 提取：

```sh
python tools/extract_stock.py "/path/to/WOBHub/resources/app.asar" --out inputs
```

工具只读固定 Rainy75 V2 资源条目并核对上述哈希，不运行应用内脚本。提取的是官方升级包，不能称为设备实际 Flash 备份；未核实的新发布目录会拒绝。

构建器根据精确输入 SHA 选择独立主控地址表；随仓 HTML 仍是旧 0x3F 基线，不能当作官方 0.64 包，所以本仓库的 `inputs/main-stock.bin` 直接随带了官方 0.64 镜像。

### 2. WCH 官方 Flash 读写库（`libISP585.a`）

编译主控固件（需要把校时数据写入 Flash）还要用到沁恒官方 SDK 里的静态库 `libISP585.a`：

- 来源仓库：[openwch/ch585](https://github.com/openwch/ch585/tree/db889195f07b8f3f4e7bf2c55f96a35daa14bebf)（指定 commit：`db889195f07b8f3f4e7bf2c55f96a35daa14bebf`）
- 仓库内文件路径：`EVT/EXAM/SRC/StdPeriphDriver/libISP585.a`
- 期望 SHA-256：`8ede32a24e09344e86ecd74731069e19d6befa287bd6de2dd7c757c6f1d06a9e`

可以直接在 GitHub 网页打开该路径点 `Raw` 下载这一个文件，放到本地 `inputs/libISP585.a`。

---

## 第三步：先生成原厂恢复包（强烈推荐）

动手编译改版固件前，先花几秒钟把原厂恢复镜像打出来备着。这步不需要 Clang 或 SDK，万一刷出问题或者想恢复出厂界面随时能救砖：

```sh
python tools/build.py main --stock inputs/main-stock.bin --restore-stock
python tools/build.py ips --stock inputs/ips-stock.bin --restore-stock
```

产物会保存在 `build/main-restore/` 和 `build/ips-restore/`，里面各有恢复用的 `.bin` 和 `manifest.json`。注意它们是用你提供的原厂 APP 加空余区域填充生成的，不是从你键盘 Flash 里读出来的个人备份。

---

## 第四步：编译自定义固件

### 1. 编译基础版屏幕固件（普通 IPS）

三套内置主题选一个：`pink`（樱花粉）、`mint`（薄荷绿）、`mono`（墨水灰）：

```sh
python tools/build.py ips --stock inputs/ips-stock.bin --theme pink
```

如果你想自定义按键图标或换字体路径，可以加上参数：

```sh
python tools/build.py ips --stock inputs/ips-stock.bin --theme mint --keys "/path/to/keys.json" --clang "C:\Program Files\LLVM\bin\clang.exe"
```

生成产物都在 `build/ips/` 下：
- `rainy75v2-ips.bin` — 待烧录的屏幕固件
- `manifest.json` — 烧录时给网页工作台核对的目标/SHA 清单
- `assets/robot-<theme>.gif` — 对应主题色的像素机器人动画（刷完要一起传进 S1 槽位）

> 这一版普通 IPS（UI `0.6.3 / L6`）保留了原显示逻辑，同时提供只读芯片容量与型号查询功能。

### 2. 编译键盘主控固件（CH585）

```sh
python tools/build.py main --stock inputs/main-stock.bin --isp-lib inputs/libISP585.a
```

如果你用的 Clang 版本较旧、不认识新版默认参数，可以加上 `--riscv-march rv32imac`：

```sh
python tools/build.py main --stock inputs/main-stock.bin --isp-lib inputs/libISP585.a --riscv-march rv32imac
```

生成产物在 `build/main/` 下：
- `rainy75v2-main.bin`
- `manifest.json`

刚刷完新主控时，里面的校时数据页是空的，屏幕时间会显示 `--:--:--`，刷好后去网页工作台点一下校时就行。

---

## 构建脚本自动帮你守住了哪些底线？

每次运行 `tools/build.py` 时，脚本都会在本地做完以下核查才输出 `.bin`：

- **输入核对**：原厂 `.bin` 和 `libISP585.a` 的 SHA-256 必须完全一致。
- **最小化修改**：原厂前 512 字节以及非声明的原始区域保持原封不动；普通 IPS 只替换指定的 8 处 `BL` 调用；主控只替换指定的 4 处跳转/调用。
- **地址防踩踏**：
  - 普通 IPS 新增代码严格限制在 `0x0807EC90..0x08080000`，模块内存限制在 `0x2005F000..0x20060000`。
  - 主控新增代码不会侵入 `0x49000`（`0x49000..0x49FFF` 专门留给 RTC 校时记录页），且 `libISP585.a` 不允许带入多余的 `.data` / `.bss` 全局静态内存。

---

## 运行自动化测试

如果你想验证本地代码和工具链是否正常（测试全在本地模拟运行，不连接真实键盘）：

```sh
python -m unittest discover -s tests -p "test_*.py"
npm test
```

更完整的测试（Playwright 网页烟雾测试、Unicorn ARM 机器码仿真）说明见 [验证文档](validation.md)。下一步刷机请看 [基础版使用指南](usage.md)。

## 已有用户按需升级

各步骤的更换范围见 [升级说明](upgrade.md)。软件版本与协议能力不能混为一谈。

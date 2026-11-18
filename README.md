# Rainy75 V2 桌面工具箱 · 社区二次开发

> 在 [**xixiaotiam1219-lab/rainy75v2-tft**](https://github.com/xixiaotiam1219-lab/rainy75v2-tft)（MIT，© 2026 xixiaotiam1219-lab）基础上二次开发的 **Windows 桌面工具箱**：
> 把「刷机向导 + 主题定制台 + 显示诊断」打包成一个双击即用的 exe，无需 Python、无需联网。
>
> 动画素材来源：[**PC2005-cloud/dsh-pet**](https://github.com/PC2005-cloud/dsh-pet)（版权归原作者，仅作内置素材示例）。

---

## 这是什么

一块 320×172 的小屏幕，装在 Rainy75 V2 键盘上。工具箱负责三件事：

| 模块 | 作用 |
| --- | --- |
| **刷机向导** `web/flash-wizard.html` | ① 预检 → ⑥ 完整 IAP 刷写：主控 → 屏幕 → S1 动画 → 校时，WebHID 直连，无需驱动 |
| **主题定制台** `studio/index.html` | 换角色素材、调配色、改状态栏，实时预览 320×172，一键重编固件 |
| **显示诊断** `web/diagnose.html` | 只读查询时钟源/电量/连接方式/累计按键；可一键「降低动画负载」 |

屏幕固件全部跑在屏内：无常驻后台、无字库上传、无网络请求。

---

## 快速开始

1. 到 [Releases](https://github.com/INDULGE00/rainy75v2-toolbox/releases) 下载 `Rainy75Toolbox-vX.Y.Z-full.exe`，双击运行。
2. 首次启动会把内置组件释放到 `%LOCALAPPDATA%\Rainy75Toolbox\app`（约 5 秒），之后秒开。
3. 打开「刷机向导」，① 预检通过后勾选 4 项确认，走完 ①→⑥。

刷机必须 **USB 数据线直连键盘 + 有线档**；2.4G / 蓝牙刷不了屏。
**刷机有风险**，先读 [免责声明](DISCLAIMER.md) 与 [恢复指南](docs/recovery.md)。

---

## 状态栏能放什么

**左侧（三选一）**

| 选项 | 说明 | 固件占用 |
| --- | --- | --- |
| 时间 | 主控 RTC 每秒同步；未校时显示 `--:--:--` | 4,804 B |
| 自定义文字 | 中英文与标点混排，**画进 S1 底图**，不占固件 | 4,780 B |
| 自定义像素图标 | 20×14 画布，按电量点亮 1~5 个，颜色跟随主题或自选 | 4,842 B |

**右侧（最多 3 项，可排序）**：连接方式、大小写、电量、打字速率、按键累计次数（5 位）、回报率、防抖。

选择或排序后**立刻**反映到「③ 实时预览」，无需先保存。

### 关于固件空间

屏幕固件只能用出厂镜像尾部 **4,976 字节**。所有可选模块按需编译，默认配置余量 134 B；超出会直接编译失败而不是生成坏固件。
因此**没有实现「像素图标每格独立颜色」**：单像素 RGB 至少 3 字节，20×14 就是 840 字节，塞不进去。当前方案是整块统一配色 + 可选跟随主题色。

---

## 动画（S1）体积

动画槽因批次而异，默认按 **512 KB** 规划。定制台上传时自动抽帧压进上限；刷机时若屏幕拒绝（**BEGIN 状态 4**），向导自动降档重试：

```
原速 → 150 ms 慢放 → 256 KB 重新生成 → 内置精简版
```

生成成功后日志会写明最终属性：

```
本次动画：60 帧 × 80 ms = 4.80 s 循环 · 512 KB · 约 2262 个数据包 · 占「512 KB」上限的 96%
```

---

## 内置快照

`toolbox/firmware/` 是刷机向导默认使用的快照，**内容为本机当前在用的固件**（蓝色主题 + 已烘焙的角色动画）：

| 文件 | 说明 |
| --- | --- |
| `ips.bin` | 屏幕固件 507,904 B（出厂 0.64 基线 + 显示补丁） |
| `ips.json` | 构建清单（SHA-256 校验用） |
| `main.bin` / `main.json` | 主控固件 294,912 B |
| `s1-full.gif` / `s1-lite.gif` / `s1-blank.gif` | 完整 / 精简 / 占位三档动画 |
| `preview.png` | 320×172 效果图 |

换回自己的固件：定制台「应用并重新编译 IPS 固件」→ 运行 `python toolbox/snapshot.py`。

---

## 内置角色素材

定制台「① 角色形象」预置两张示例，点一下即可套用：

- **DeepSeek** — 深蓝女仆（鲸鱼围裙）
- **Claude** — 橘发书卷（花朵发饰）

素材来源：[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)。
也可以拖自己的 GIF / PNG，静态白底图会自动拆三视图并去白底。

---

## 目录结构

```
firmware/ips/     屏幕固件补丁（C，无 SDK）
firmware/main/    主控时钟桥补丁
tools/            构建器、素材生成、定制台后端
web/              刷机向导、诊断页
studio/           主题定制台（presets/ 为内置素材）
profiles/         字库、按键字形、主题与状态栏配置
inputs/           原厂编译输入（SHA-256 逐个核对）
toolbox/          桌面 exe、payload、内置快照
tests/            Python + Node 测试
vendor/           原厂离线烧录网页（非 MIT）
```

---

## 开发

```bash
python tools/build.py ips  --stock inputs/ips-stock.bin --clang <clang> --theme pink
python tools/build.py main --stock inputs/main-stock.bin --isp-lib inputs/libISP585.a --clang <clang>
python toolbox/snapshot.py      # 把 build/ 冻结进 toolbox/firmware
python -m unittest discover -s tests -p 'test_*.py'
npm test
python toolbox/make_exe.py      # 打包 exe
```

`.text` 硬上限 4,976 字节，超出即链接失败（有意为之，防止刷坏屏幕）。

---

## 许可与致谢

- 上游：[xixiaotiam1219-lab/rainy75v2-tft](https://github.com/xixiaotiam1219-lab/rainy75v2-tft)（MIT）
- 动画素材：[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)
- 本项目自有代码（`firmware/`、`tools/`、`web/`、`studio/`、`toolbox/`）同样以 MIT 发布，见 [LICENSE](LICENSE)
- `vendor/` 下原厂烧录网页版权归原厂，**不在 MIT 覆盖范围**，见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)

固件刷写属于对硬件的不受支持修改，风险自负。

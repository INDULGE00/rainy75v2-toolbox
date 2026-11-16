# 测试与验证说明

仓库提供两层纯本地的自动化检查（都不需要连接真实键盘），这里把「自动测试覆盖了什么」和「实机上还差什么」摆清楚。

---

## 1. 基础自动化单元测试（CI 每次必跑）

```sh
python -m unittest discover -s tests -p "test_*.py"
npm test
python tools/check_release.py
```

不需要原厂固件或 Clang，也不碰真实硬件。目前覆盖：

- **协议与烧录安全**：`BE 1A` / `BE E4` 帧长度和校验、旧版 `0x0357` ACK 兼容、错误目标芯片拒绝擦写、IAP 全字节及末尾重叠块校验、旧固件写入前拦截、GIF 上传尺寸检查与覆盖确认、带 `variant` 的旧歌词版清单会被拒绝。
- **素材**：三套内置主题 GIF 逐帧校验（全帧 320×172、`disposal=1`、不透明及标记像素 `(22, 39)`），并检查解码像素与绘图源码一致、仓库素材与生成器一致；拒绝恢复背景或增量矩形的回归文件。另有大图标尺寸和居中检查。
- **原厂提取**：`tests/test_extract_stock.py` 用构造的小样本校验 `extract_stock.py` 的解析与 SHA-256 白名单，不放任何原厂二进制进测试。
- **发布边界**：`tools/check_release.py` 检查 Git 可见文件里没有意外的私密数据或缺失的 Markdown 链接。

---

## 2. 无头浏览器 UI 烟雾测试（可选）

安装 Playwright（只是拿来自动点页面和截屏）：

```sh
npm install --no-save --package-lock=false playwright@1.56.1
npx playwright install chromium
node tests/browser.smoke.mjs
```

如果本地已经有 Chrome 或 Edge，可以用环境变量 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 指定可执行文件路径。测试用 Mock WebHID 检查：

- 桌面端与手机端页面布局是否错位溢出；
- 像素工作台编辑/导出 `keys.json`、模拟 `V7.1` 对时流程以及旧固件拦截提示（生成 `assets/studio.png`）。

---

## 3. 本地 ARM 指令级仿真（需要 Unicorn）

用 Unicorn 直接跑编译出来的真实 Cortex-M4 机器码（只有主控时钟桥有模型用例）：

```sh
python -m pip install -r requirements-model.txt
python tools/test_main_model.py
python tools/test_gif_disposal_model.py --stock inputs/ips-stock.bin
```

`test_gif_disposal_model.py` 会接管并模拟底层 FatFs、动态内存分配器、LCD DMA 忙标志和串口发送，执行原厂初始化及处置分支，验证 `disposal=2` 清帧面与 `disposal=1` 保留帧面的差异；它在文件读取与 LZW 解码开始前停止，不含第三方固件。

---

## 示例机器人闪烁的离线复现

旧公开示例每帧都是完整不透明图，但采用 `disposal=2`。对匹配 SHA 的原厂 IPS 执行真实 reset 初始化后，GIF 解码入口 `0x0805A54C` 跳到 RAM 的 `0x2003EE74`；其中 `0x2003EE7C..0x2003EF28` 在上一帧处置方式为 2 时，先用背景色清空 RGB565 帧面。

两次 worker 调用之间，`firmware/ips/native_ui.c` 的 `rainy_hook_image` 会在按键/状态变化时复用同一帧面进行脏刷新；这时若底图刚被处置方式 2 清空，刷新只补上动态字母与顶栏，机器人和边框便一起消失，直到下一轮转换恢复。`disposal=1` 保留上一张完整底图，避开这个窗口。

---

## 4. 已经做过的实机记录

- **基础版**：在单台开发设备上完成主控与屏幕两次全字节烧录校验，按键（含 Shift 上档符号）、电量、USB / 2.4G / 蓝牙图标与原创机器人显示正常；校时读回主控与屏幕秒数一致，间隔两秒读回继续走时，屏幕时钟源状态为 `0x0402`。
- **未覆盖**：休眠、模式切换与完全断电保时依赖各批次供电条件，尚未测遍；RTC 计数在完全断电后可能归零，需要 USB 重新校时。

---

## 5. 明确没有验证的部分

- 不同批次的外置 Flash 容量、屏幕面板差异与按键主控版本只在一台设备上确认过。
- 自动测试、浏览器烟雾测试与指令级仿真的结果**不能写成实机实测**；本文档区分「代码编过」「模型跑通」「真键盘上亮了」三种证据。
- 本项目为社区实验项目，不承诺固定帧率、输入延迟或保时精度。

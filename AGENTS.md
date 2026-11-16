# Agent 协作说明

接手本仓库任务前，请先读完 `README.md` 和任务对应的 `docs/` 文档。

## 必须先搞清的两个边界

1. **两颗芯片不要混为一谈**：键盘主控是 **CH585（RISC-V）**，屏幕控制芯片是 **AT32F435（ARM Cortex-M4）**。两者的内存布局、编译器参数、固件大小和 IAP PID 完全不同。
2. **本分支只有基础屏幕版**：`firmware/ips/`（屏幕）与 `firmware/main/`（主控），构建到 `build/ips/` 与 `build/main/`。上游的歌词播放器扩展（`firmware/ips-lyrics/`、`desktop/`、字库与后台）已整体移除，**不要把它加回来**，也不要引入字库依赖、Windows 常驻后台或除「校时/上传/烧录」之外的设备指令。

## 编码与安全准则

- **严禁私自操作硬件**：除非用户在指令中明确要求并授权连接设备、写入或烧录，否则只交付源码、构建产物、预览图和测试结果。已有明确授权时按要求执行即可。
- **不要绕过安全校验**：绝不允许通过删除原厂文件 SHA-256 检查、Target/PID 检查、Chip Flash 容量检查或 ROM/RAM 地址边界断言来强行“让构建或刷机通过”；不要猜测未验证的空闲内存、GPIO 或恢复按键。
- **区分测试层级**：模拟测试（`npm test`）、无头浏览器模拟（Playwright）和指令级仿真（Unicorn `test_main_model.py` / `test_gif_disposal_model.py`）的结果**不能写成实机实测**。官方0.64基线已有单台设备刷写与校时读回，不把它写成全批次、完全断电或完整BLE验证。
- **保持低侵入设计**：日常显示优先复用键盘原生通知和屏幕本地缓存动画，不要往桌面端添加全局键盘钩子或常驻后台。
- **守住第三方与隐私边界**：从 `v1.2.0` 起仓库按需附带固件包 —— [vendor/](vendor/README.md) 的原厂烧录 HTML、`inputs/`（解出的原厂 `.bin` 与 `libISP585.a`）、`toolbox/firmware/`（内置固件快照）。这些内容**均非 MIT**，保持原样、勿修改或重新标为 MIT；除此之外，绝不新增提交 `build/` 产物、`llvm/` 工具链、个人设备序列号、日志、私人角色图或本机绝对路径。在未明确要求检查烧录网页本身时，也不要把 `vendor/*.html` 里的百万字节编码固件读入/塞进云端 AI 上下文。必须保留 `LICENSE` 原署名，字体保持 OFL-1.1，Elog 保留上游 MIT 声明。

## 验证命令

改动代码或文档后，按情况跑对应的检查：

```sh
python -m unittest discover -s tests -p "test_*.py"
npm test
python tools/check_release.py
```

本仓库已附带 `inputs/` 与原厂 HTML，本机有 Clang 时可直接运行 `tools/build.py` 验证固件能否正常编出并检查补丁范围。没有编译器时如实说明“未构建固件”，不要编造结果。

## 功能与升级范围

只有一种发布形态：基础屏幕版（按键、时钟、电量、连接图标、机器人）+ 桌面工具箱（刷机向导 / 主题定制台 / 显示诊断）。

主控0.63 beta1与官方0.64按 tools/main_profiles.py 的精确SHA选择不同地址，不能靠版本标签套地址。屏幕能力 `L6`、主控能力 `V7.1`；工具只发校时、素材上传与 IAP 烧录三类指令。

`toolbox/firmware/` 是刷机向导默认使用的内置快照，由 `python toolbox/snapshot.py` 从 `build/` 生成；改了固件或主题后要重新生成，再 `python toolbox/make_exe.py` 重打包。`inputs/` 与 `toolbox/firmware/` 属于非 MIT 的原厂派生内容，只在本地生成固件用。

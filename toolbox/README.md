# Rainy75 V2 工具箱（离线桌面版）

把「刷机向导 + 主题定制台 + 显示诊断」装进一个窗口，全程本机 `127.0.0.1`，**不需要联网**。

## 方式一：直接用 exe（推荐，无需 Python）

双击 **`dist\Rainy75Toolbox.exe`**（约 100 MB，单文件，自带固件包与编译器）。首次运行会把内置组件释放到
`%LOCALAPPDATA%\Rainy75Toolbox\app`（约 5 秒），之后每次启动都是秒开。

> **开箱即刷（默认）**：`python toolbox/make_exe.py` 打出来的包会把 `inputs/`、`build/`、
> `toolbox/firmware/` 和 clang 一起塞进去，双击就能 ①→⑥ 直接刷，不用先导 `ips-stock.bin`，
> 也不用另外装编译器。
>
> 如果你需要一款**不含原厂固件**的分发版（例如公开给别人、但只让别人用自己的原厂文件）：
>
> ```
> python toolbox/make_exe.py --compliant --out-name Rainy75Toolbox-lite
> ```
>
> 这种包约 21 MB，首次使用需要在定制台 ⓪ 导入自己的 `ips-stock.bin`，要重新编译主题还需自备 clang。

- 不需要安装 Python、不需要 `pip install`、不需要联网；
- 自带 clang + lld，**主题定制台里改完配色/GIF 可以直接重新编译固件**；
- 关闭那个应用窗口 = 退出程序（后台服务随之停止，不留残留进程）；
  如果页面是在普通浏览器标签里打开的，用页头右上角的 **「退出程序」** 按钮停服务；
- 换一台电脑直接用：整个软件自包含，只要那台机器有 Chrome 或 Edge（Windows 10/11 自带 Edge）。
  程序会优先用应用窗口模式打开，打不开就退回默认浏览器；两者都没有会弹窗给出网址。
- 只监听 `127.0.0.1`，并把回环地址加入 `NO_PROXY`，所以**系统里开着 Clash / v2ray / 公司代理
  也不影响**；
- **双击无窗口的真正元凶（本版已修）**：PyInstaller 的 `console=False` 构建里
  `sys.stdout` / `sys.stderr` 是 `None`，而 `http.server` 每处理一个 `/api/` 请求都会往
  stderr 写一行访问日志 → `AttributeError` → 连接被丢弃 → 程序自己的启动自检永远失败。
  修法是在入口把 stdio 重定向到 `logs/console.log`（`ensure_stdio()`），并给
  `studio.Handler.log_message` 加 `sys.stderr is not None` 保护。
  从命令行（带控制台）启动永远测不出这个问题，所以验证必须用「无控制台」方式。
- 端口被占用时自动顺延到 8767、8768…（最多试 20 个）；
- 日志：`logs/toolbox.log`（各阶段与页面自检）、`logs/console.log`（原 stdout/stderr，含 HTTP
  访问日志与异常栈）。启动失败也会弹窗提示。

重新打包（改了网页/固件/主题后）：

```
python toolbox/snapshot.py               # 先把你刚编出来的 build/ 冻结成内置快照
python toolbox/make_exe.py               # 重新生成 dist\Rainy75Toolbox.exe（含固件包 + clang）
python toolbox/make_exe.py --payload     # 只更新载荷，不跑 PyInstaller
python toolbox/make_exe.py --no-clang    # 含固件包、不带编译器的精简版
python toolbox/make_exe.py --compliant   # 不含原厂固件与编译器的分发版
```

打包产物都是自包含的：`payload.zip` 里装着 tools / web / studio / profiles / inputs /
build / firmware 源码 + 内置固件快照（`toolbox/firmware/`）+ 当前角色素材 + 裁剪到最小的工具链
（clang 113 MB 与 ld.lld 76 MB）。`app_main.py` 是 exe 的入口，`Rainy75Toolbox.spec` 是 PyInstaller 配置。

## 方式二：有 Python 环境时用 .bat

双击项目根目录的 **`Rainy75工具箱.bat`**。

它会：① 在 `127.0.0.1:8766` 起一个本地服务（定制台服务顺带托管整个项目）；
② 用 Chrome / Edge 的**应用窗口模式**（`--app`，无地址栏）打开工具箱；
③ 保留那个黑窗口 —— 关掉它（或 Ctrl+C）服务才停。

命令行等价方式：

```
python toolbox/launch.py                 # 启动 + 打开窗口
python toolbox/launch.py --check         # 只自检（5 个页面是否 200）然后退出
python toolbox/launch.py --port 8790     # 换端口
python toolbox/launch.py --no-browser    # 只起服务，自己开浏览器
```

端口 8766 已被占用且是本项目服务时会直接复用，不会再起第二个。

## 日常更换：用「快捷操作」，不用从头刷

屏幕固件、S1 动画、RTC 时间是设备上**三块互不影响的存储**，所以大部分日常操作根本不需要
重刷主控（① ②），也不需要走完整 ①→⑥：

| 你的目的 | 需要做 | 大概耗时 |
|---|---|---|
| 只改时间 | ⑥ 校时 | 几秒 |
| 只换屏幕上的角色动画 | ⑤ 上传 S1 | 几秒 ~ 几分钟（看帧数与包数） |
| 只换配色 / 图标 | ③④ 重刷屏幕固件 | 约 1 分钟 |
| 换配色 + 换动画 | ③④ + ⑤ | 1~3 分钟 |
| 第一次使用、换主控基线、救砖 | 完整 ①→⑥ | 约 3~5 分钟 |

向导里那块「快捷操作（日常更换不用从头刷）」就是这四个入口，点一下会按顺序自动执行对应步骤，
仍然沿用完整流程的同一套校验与回读验证，只是不再要求你在本次会话里先走完前面的步骤。
仍然需要先勾选 4 项确认解锁，避免误触。

前提：主控已经是 **V7.1**（即之前完整刷过一次）。若提示「主控不是 V7.1 / 屏幕协议不匹配」，
说明那台键盘还是原厂固件，走一次完整 ①→④ 之后再回到快捷操作即可。

## 三个标签页

| 标签 | 地址 | 作用 |
|---|---|---|
| 刷机向导 | `/web/flash-wizard.html` | ①→⑥ 六步刷机：主控 IAP、烧主控、屏幕 IAP、烧屏幕、上传 S1、校时 |
| 主题定制台 | `/studio/index.html` | 上传角色 GIF、调主题色、实时预览、重新编译 IPS |
| 显示诊断 | `/web/diagnose.html` | 只读状态、协议自检 |

嵌入页面里如果**设备选择器不弹出**（个别浏览器不允许 iframe 调用 WebHID），点右上角
**「在新标签打开」**，页面会以顶层窗口打开，功能完全一样。

## 固件来源（向导里的三个选项）

| 选项 | 读哪里 | 说明 |
|---|---|---|
| **内置快照（推荐）** | `toolbox/firmware/` | 仓库随附的那套固件（`v1.2.0` 起默认打包），离线可用，不用导原厂文件 |
| build/ 最新编译 | `build/main`、`build/ips` | 定制台刚重编完想直接刷，选这个 |
| 自选本地文件 | 你磁盘上的 `.bin` / `.gif` | 留空的项目自动回落为内置快照 |

- 主控 `.bin` 必须是 **294,912 B**，屏幕 `.bin` 必须是 **507,904 B**，长度不对预检直接拒绝。
- 自定义固件**无法核对官方 0.64 基线 SHA**，预检会打一行黄色警告，来源正确性需自己确认；
  长度、目标、IAP PID、SHA-256 仍然会校验。
- `build/` 快速重编后想「冻结」成新的内置快照：

```
python toolbox/snapshot.py
```

它会重新写入 `toolbox/firmware/`（main.bin / ips.bin / s1-full.gif / s1-lite.gif / s1-blank.gif /
preview.png / info.json），页头的「快照」徽标随之更新。

## 目录

```
toolbox/
  launch.py        启动器（起服务 + 开应用窗口 + 自检）
  snapshot.py      把 build/ 当前固件冻结成快照
  index.html       工具箱外壳（标签页 + 状态徽标）
  app.mjs  style.css
  firmware/        内置固件快照（勿手工改，用 snapshot.py 生成）
```

## 注意

- 刷机必须 **USB 数据线直连键盘本体 + 有线模式**，2.4G / 蓝牙刷不了屏。
- 每次改完主题在定制台点「应用并重新编译」，固件 SHA 会变；只换了主题色而没重刷第 ④ 步，
  屏幕上看到的还是旧配色。
- 关掉黑窗口 = 服务停止，工具箱页面会失联（刷新即报无法连接）。

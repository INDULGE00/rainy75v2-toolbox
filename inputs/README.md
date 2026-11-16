# 编译输入（随仓库一起分发）

本版为了「开箱即刷」把原厂编译输入直接放进仓库了，所以定制台的「应用并重新编译」和刷机向导都不用你自己再去导出固件。文件来源与校验值如下：

| 文件 | 是什么 | 大小 | SHA-256 |
| --- | --- | --- | --- |
| `ips-stock.bin` | 原厂屏幕固件 `0x0002` | 502,925 B | `32defab7…12b77f41` |
| `main-stock.bin` | **官方 0.64 主控固件 `0x40`（默认基线）** | 284,492 B | `31a9eb80…26f0e476` |
| `main-stock-063beta1.bin` | 旧原厂主控固件 `0x3F`（beta1，旧设备兼容用） | 284,488 B | `bc575a6d…90f4d23b` |
| `libISP585.a` | WCH CH585 官方 SDK 的 Flash 读写静态库 | 5,722 B | `8ede32a2…1d06a9e` |

`ips-stock.bin` 与 `main-stock-063beta1.bin` 可由仓库自带的 [vendor/Rainy75V2烧录工具20261112-1beta1.html](../vendor/README.md) 解出（`tools/extract_stock.py` 只读内嵌数据、不执行网页脚本）。`main-stock.bin`（0.64）取自 WOBHub 客户端 `20261113-1` 的官方资源，脚本同样按 SHA-256 核对；`libISP585.a` 取自 [openwch/ch585](https://github.com/openwch/ch585) 指定 commit。

> **为什么必须放 0.64**：刷机向导的严格预检只接受官方 0.64 基线的主控构建（`stockSha256 = 31a9eb80…`、`stockVersion = 0.64`），拿 0x3F 编出来的 `.bin` 会报「主控基线不是官方 0.64，拒绝刷写」。两套镜像**不要同名覆盖**。

`build.py` 按输入 SHA 自动选地址表，所以两种基线都能编，只是文件名必须区分：

```sh
python tools/build.py main --stock inputs/main-stock.bin        --isp-lib inputs/libISP585.a   # 官方 0.64
python tools/build.py main --stock inputs/main-stock-063beta1.bin --isp-lib inputs/libISP585.a # 旧 0x3F
```

> 这些文件里的原厂固件归 WOB 原厂所有，**不适用 MIT 协议**，只用于在本机生成补丁固件；请勿单独再分发，也不要改动后重新标为 MIT。风险与边界见 [DISCLAIMER.md](../DISCLAIMER.md) 与 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

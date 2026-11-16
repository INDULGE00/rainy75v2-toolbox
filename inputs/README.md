# 编译输入（随仓库一起分发）

本版为了「开箱即刷」把原厂编译输入直接放进仓库了，所以定制台的「应用并重新编译」不用你自己再去导出固件。文件来源与校验值如下：

| 文件 | 是什么 | 大小 | SHA-256 |
| --- | --- | --- | --- |
| `ips-stock.bin` | 原厂屏幕固件 `0x0002` | 502,925 B | `32defab7…12b77f41` |
| `main-stock.bin` | 原厂键盘主控固件 `0x3F`（beta1 基线） | 284,488 B | `bc575a6d…90f4d23b` |
| `libISP585.a` | WCH CH585 官方 SDK 的 Flash 读写静态库 | 5,722 B | `8ede32a2…1d06a9e` |

`ips-stock.bin` 与 `main-stock.bin` 由仓库自带的 [vendor/Rainy75V2烧录工具20261112-1beta1.html](../vendor/README.md) 解出（`tools/extract_stock.py` 只读内嵌数据、不执行网页脚本），SHA-256 与 `tools/build.py` 里的白名单一致才会参与编译。`libISP585.a` 取自 [openwch/ch585](https://github.com/openwch/ch585) 指定 commit。

> 这些文件里的原厂固件归 WOB 原厂所有，**不适用 MIT 协议**，只用于在本机生成补丁固件；请勿单独再分发，也不要改动后重新标为 MIT。风险与边界见 [DISCLAIMER.md](../DISCLAIMER.md) 与 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

需要重新导出（例如官方出了新基线）时：

```sh
python tools/extract_stock.py "vendor/Rainy75V2烧录工具20261112-1beta1.html" --out inputs
```

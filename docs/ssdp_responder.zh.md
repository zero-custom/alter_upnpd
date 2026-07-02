# ssdp_responder.py — SSDP 发现协议

处理 UPnP 设备发现，基于 SSDP（Simple Service Discovery Protocol）：定期多播 NOTIFY 公告和 M-SEARCH 响应。

## 模块常量

`UPNP_NT_LIST` — 集中管理 8 个 UPnP 设备/服务类型列表，`SSDPResponder`（NOTIFY 通告）和 `SSDPHandler`（M-SEARCH 响应）共享使用。增删 UPnP 服务仅需改动此常量。

| # | NT | USN 后缀 |
|---|----|---------|
| 1 | `upnp:rootdevice` | `::upnp:rootdevice` |
| 2 | `urn:schemas-upnp-org:device:InternetGatewayDevice:1` | `::urn:...:InternetGatewayDevice:1` |
| 3 | `urn:schemas-upnp-org:device:WANDevice:1` | `::urn:...:WANDevice:1` |
| 4 | `urn:schemas-upnp-org:device:WANConnectionDevice:1` | `::urn:...:WANConnectionDevice:1` |
| 5 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` | `::urn:...:Layer3Forwarding:1` |
| 6 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` | `::urn:...:WANCommonInterfaceConfig:1` |
| 7 | `urn:schemas-upnp-org:service:WANIPConnection:1` | `::urn:...:WANIPConnection:1` |
| 8 | `urn:schemas-upnp-org:service:WANPPPConnection:1` | `::urn:...:WANPPPConnection:1` |

## SSDPResponder

在所有非回环 IPv4 接口上创建 UDP 数据报端点，加入 SSDP 多播组，定期发送 `ssdp:alive` NOTIFY 消息。使用 `ssdp` 库（`ssdp.aio.SimpleServiceDiscoveryProtocol`）。

### 周期性 NOTIFY `ssdp:alive`

每 `EnvConfig.ssdp_notify_interval` 秒（默认 180s），`_send_alive()` 遍历 `UPNP_NT_LIST`，为每个条目发送一条 NOTIFY。每个 NT 有独立的 try/except 块——某个条目发送失败不影响其他条目。

每条 NOTIFY 包含以下头：

| 头 | 值 |
|---|---|
| `HOST` | `239.255.255.250:1900` |
| `NT` | （来自 `UPNP_NT_LIST`） |
| `NTS` | `ssdp:alive` |
| `USN` | 根据 NT 条目推导 |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `CACHE-CONTROL` | `max-age=1800` |
| `SERVER` | `Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0` |
| `BOOTID.UPNP.ORG` | 基于时间戳的启动 ID（重启后变化） |
| `CONFIGID.UPNP.ORG` | `1`（静态——无运行时配置变更） |

关闭时，`_send_byebye()` 发送全部 8 条消息，`NTS: ssdp:byebye`。

### M-SEARCH 处理

`SSDPHandler` 继承自 `aio.SimpleServiceDiscoveryProtocol`。ST→USN 映射表（`_ST_USN_MAP`）通过 dict comprehension 从 `UPNP_NT_LIST` 推导。

1. `request_received()` 解析 `ST`（Search Target）头。
2. 在 `_ST_USN_MAP` 中查找对应的 USN。
3. 调用 `_send_search_response()` 回复。

**匹配逻辑：**

| 请求 `ST` | 响应行为 |
|---|---|
| 特定类型（如 `upnp:rootdevice`、`urn:...:WANIPConnection:1`） | 单条 200 OK 响应，USN 匹配 |
| `ssdp:all` | 8 条响应，每种设备/服务类型各一条 |

### 设备生命周期标识符

| 标识符 | 值 | 说明 |
|---|---|---|
| `BOOT_ID` | `int(time.time())` | 每次重启更新。用于 `BOOTID.UPNP.ORG` 头。 |
| `CONFIG_ID` | `1` | 静态。 |

### 启动流程

1. 通过 `/sys/class/net/`（ioctl）枚举非回环 IPv4 接口。
2. 对每个接口，创建 UDP 数据报端点，以 `SSDPHandler` 作为协议。
3. 发送初始 `ssdp:alive` NOTIFY 突发。
4. 进入循环：休眠 1 秒，检查 `notify_interval` 是否已到，如是则发送 NOTIFY。

### 失败模式

- **PermissionError**：无法绑定 1900 端口——需要 `CAP_NET_BIND_SERVICE` 或 root。记录警告，该接口上继续但不提供 SSDP。
- **无非回环接口**：不发送任何 SSDP 通知。
- **多播加入失败**：记录警告，但套接字仍可用于发送。

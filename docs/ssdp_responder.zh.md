# ssdp_responder.py — SSDP 发现协议

处理 UPnP 设备发现，基于 SSDP（Simple Service Discovery Protocol）：为根设备发送定期的多播 NOTIFY 公告。

## `SSDPResponder`

在所有非回环 IPv4 接口上创建 UDP 数据报端点，定期发送 `ssdp:alive` NOTIFY 消息。使用 `ssdp` 库（`ssdp.aio.SimpleServiceDiscoveryProtocol`）。

### 周期性 NOTIFY `ssdp:alive`

每 30 秒发送一次针对 `upnp:rootdevice` 的多播 NOTIFY：

| 头 | 值 |
|---|---|
| `HOST` | `239.255.250.250:1900` |
| `NT` | `upnp:rootdevice` |
| `NTS` | `ssdp:alive` |
| `USN` | `uuid:ed8d683a-91ea-402b-9c25-d0a48f23e9d7::upnp:rootdevice` |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `CACHE-CONTROL` | `max-age=1800` |
| `SERVER` | `Linux/2.6.18 UPnP/1.0 alter_upnpd/1.0` |

### M-SEARCH 处理

`SSDPHandler` 继承自 `aio.SimpleServiceDiscoveryProtocol`。当前实现的 `response_received`、`request_received` 和 `_send_response` 方法均为空操作（no-op）。M-SEARCH 响应尚未实现。

## 启动流程

1. 通过 `netifaces` 枚举非回环 IPv4 接口。
2. 对每个接口，创建 UDP 数据报端点，以 `SSDPHandler` 作为协议。
3. 进入循环：休眠 30 秒，然后为每个接口发送一个 `ssdp:alive` NOTIFY。

## 失败模式

- **PermissionError**：无法绑定特权端口（不太可能——使用临时端口）。如果某个接口的 SSDP 失败，会记录日志并继续处理剩余接口。
- **无非回环接口**：不发送任何 SSDP 通知。

# stun_client.py — STUN 外网 IP 解析

通过 STUN 协议发现 WAN（外网）IP 地址。通过 `AppLifecycle` 在后台守护线程中解析 IP，之后每 24 小时刷新一次。

## 类：`StunClient`

### 构造参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `stun_server` | `"stun.l.google.com:19302"` | STUN 服务器 host:port。 |
| `retries` | `4` | 每次刷新周期的最大重试次数。 |
| `refresh_interval` | `86400` | 刷新间隔（秒，24 小时）。 |
| `fallback_wan_ip` | `"192.0.2.1"` | STUN 解析失败时返回的 IP。 |

### 方法

| 方法 | 返回值 | 说明 |
|---|---|---|
| `start()` | `None` | 启动后台刷新守护线程。幂等。清除 ready 事件。由 `AppLifecycle.start()` 调用。 |
| `get_wan_ip()` | `str` | 返回最近发现的外网 IP。线程安全。首次成功解析前返回 fallback `192.0.2.1`。 |
| `wait_ready(timeout=10.0)` | `bool` | 阻塞直到首次 STUN 刷新完成。`True`=就绪，`False`=超时。 |
| `reset_cache()` | `None` | 将 WAN IP 重置为 fallback 并清除 ready 事件。仅用于测试。 |

### 刷新流程

1. 从 `stun_server` 解析 STUN 服务器地址和端口。
2. 调用 `py3stun.get_ip_info()`，最多重试 `retries` 次。
3. 成功时：在锁保护下保存外网 IP，记录日志，设置 ready 事件。
4. 失败时（所有重试用尽）：保留之前的值（或 fallback），记录警告日志。
5. 休眠 `refresh_interval`（86400 秒 = 24 小时），然后从第 1 步重复。

## 与 AppLifecycle 的集成

`AppLifecycle.start()` 调用 `stun_client.start()`，然后通过 `wait_ready()` 等待最多 10 秒，等待首次 STUN 解析完成后才启动 SSDP。这确保了在 UPnP 客户端发现设备之前 WAN IP 已解析完成——避免客户端收到 fallback IP `192.0.2.1`。

## 与 SOAP 处理器的集成

`GetExternalIPAddress` SOAP 动作在 STUN 启用时调用 `stun_client.get_wan_ip()`。禁用时（`STUN=false`），`stun_client` 为 `None`，处理器返回 `192.0.2.1`。

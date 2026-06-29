# lifecycle.py — 后台服务生命周期

管理后台服务的启动和关闭：SSDP 响应器和租期清理线程。

## AppLifecycle

### 构造参数

| 参数 | 说明 |
|---|---|
| `gost_client` | GOST API 客户端（传递给租期清理）。 |
| `get_location_fn` | 返回设备位置 URL（`http://{ip}:{port}/rootDesc.xml`）。 |
| `ssdp_notify_interval` | SSDP NOTIFY 通告间隔（秒）。 |
| `lease_cleanup_interval` | 租期清理扫描间隔（秒）。 |
| `acl_enabled` | ACL 是否启用（启动时记录日志）。 |
| `acl_allowed_subnets` | 允许的子网（启动时记录日志）。 |
| `version` | 应用版本字符串（启动时记录日志）。 |
| `shutdown_timeout` | 关闭时等待 SSDP 线程的最大秒数。 |

### 方法

| 方法 | 返回值 | 说明 |
|---|---|---|
| `shutdown_event`（属性） | `threading.Event` 或 `None` | 用于通知后台线程关闭的事件。 |
| `start()` | `threading.Event` | 启动 SSDP 和租期清理线程。返回 shutdown 事件。 |
| `stop()` | `None` | 触发关闭信号，发送 SSDP byebye，等待线程结束。 |

### 线程

| 线程 | 名称 | 守护线程 | 功能 |
|---|---|---|---|
| SSDP 响应器 | `ssdp` | 否 | 运行 `asyncio.run(SSDPResponder.start())`。关闭时等待结束。 |
| 租期清理 | `lease-cleanup` | 是 | 轮询 `GostClient.get_expired_services()`，删除过期条目，休眠。 |

### 启动流程

1. 记录版本、设备位置、GOST API URL、ACL 状态。
2. 创建 `threading.Event` 用于关闭信号。
3. 启动 SSDP 响应器线程。
4. 启动租期清理守护线程。
5. 返回 shutdown 事件。

### 关闭流程

1. 设置 shutdown 事件。
2. 通过 `SSDPResponder` 发送 SSDP `ssdp:byebye`。
3. 等待 SSDP 线程结束（最多 `shutdown_timeout` 秒）。

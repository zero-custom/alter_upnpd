# gost_client.py — GOST REST API 客户端

封装 GOST `/config/services` API，提供端口映射的增删查改、Prometheus 指标采集和服务端健康检查。重构为四个独立 seam，提升可测试性和单一职责。

## 模块架构

```
GostTransport          — 底层 HTTP 传输（认证、重试、超时）
PortMappingRepository  — 端口映射增删查改 + 缓存 + 租期过期
GostMetricsClient      — Prometheus 指标发现、抓取、解析
GostClient             — 薄门面（向后兼容）
SpeedTracker           — 每服务流量速率计算
PrometheusMetrics      — 解析后的指标快照对象
```

## 错误处理

| 异常 | 触发条件 |
|---|---|
| `GostConnectionError` | 连接/超时错误（可重试——2 次尝试，指数退避） |
| `GostApiError` | HTTP 错误（4xx/5xx）和 JSON 解码错误（不可重试） |

## `GostTransport`

底层 HTTP 传输。处理认证、重试和超时。`PortMappingRepository` 和 `GostMetricsClient` 共享此传输层。

```python
transport = GostTransport(base_url, timeout=10, retries=2, username="", password="")
transport.request("GET", "/config/services")

# 连通性检查
transport.is_available()  # 用 5 秒超时 ping /config/services
```

## `PortMappingRepository`

端口映射 CRUD 操作，带服务缓存和租期过期检查。职责单一：向 GOST API 读写端口映射。

| 方法 | 说明 |
|---|---|
| `get_services()` | 获取所有服务。有缓存（30s TTL）。失败返回 `[]`。 |
| `add_port_mapping(...)` | 单次 POST 到 `/config/services`，内联 `forwarder.nodes`。 |
| `update_port_mapping(...)` | PUT `/config/services/{name}` 原地更新（刷新 `created_at`）。 |
| `delete_port_mapping(port, protocol)` | 名称 `upnp_{port}_{protocol}`，DELETE。404 静默吞掉。 |
| `get_port_mappings()` | 过滤 `metadata.upnp == True`，从 metadata 读取。 |
| `get_port_mapping_by_index(index)` | 第 N 个映射或 `None`。 |
| `has_port_mapping(port, protocol)` | 遍历映射查找匹配。 |
| `get_expired_services()` | 返回 `now >= created_at + lease_duration` 的服务列表。 |

## `GostMetricsClient`

Prometheus 指标发现、抓取和解析。独立 seam——仅需指标的场景（如 webui 统计）可直接注入此模块，无需依赖 CRUD 层。

| 方法 | 说明 |
|---|---|
| `fetch_metrics()` | 抓取并解析 Prometheus 文本。返回 `PrometheusMetrics` 或 `None`。 |
| `discover_metrics_url()` | 从 GOST API 根路径自动发现 metrics 端点。 |

## `GostClient`（门面）

组合 `PortMappingRepository` 和 `GostMetricsClient` 的薄门面。既有调用方无需改动即可继续使用。新代码可直接注入 repository 或 metrics client。

## `SpeedTracker`

按服务的流量速率计算，基于字节计数器和可配置的滑动窗口。

## `PrometheusMetrics`

解析后的 Prometheus 指标快照。提供类型化的 gauge 值访问器。

## 命名规则

| 实体 | 格式 | 示例 |
|---|---|---|
| Service 名称 | `upnp_{port}_{protocol}` | `upnp_8080_tcp` |

## 元数据存储

```json
{
  "metadata": {
    "upnp": true,
    "external_port": 12345,
    "internal_port": 8080,
    "internal_client": "192.168.1.100",
    "protocol": "tcp",
    "description": "BitTorrent",
    "remote_host": "",
    "enabled": true,
    "lease_duration": 0,
    "created_at": 1700000000
  }
}
```

## 重试行为

`GostTransport._request()` 对 `ConnectionError` 和 `Timeout` 最多重试 2 次，使用指数退避。HTTP 错误和 JSON 解码错误立即抛出。

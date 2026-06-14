# gost_client.py — GOST REST API 客户端

封装 GOST `/config/services` API，提供端口映射的增删查改和服务器健康检查。

## 错误处理

使用类型化异常类代替字典返回值：

| 异常 | 触发条件 |
|---|---|
| `GostConnectionError` | 连接/超时错误（可重试——2 次尝试，指数退避） |
| `GostApiError` | HTTP 错误（4xx/5xx）和 JSON 解码错误（不可重试） |

调用方可使用 `try/except`。`get_services()` 和 `is_available()` 内部捕获异常，返回安全默认值。

## `GostClient`

每个应用一个实例。持有 TTL 为无限的服务缓存（`_services_cache`），每次写操作（add/delete）时清空。

## 方法

| 方法 | 说明 |
|---|---|
| `is_available()` | 用 5 秒超时 ping `/config/services`，返回 `True`/`False`。 |
| `get_services()` | 从 GOST 获取所有服务。有缓存。失败返回 `[]`。兼容 list、dict.data 和嵌套响应格式。 |
| `add_port_mapping(external_port, internal_port, internal_client, protocol, description, remote_host, enabled, lease_duration)` | 单次 POST 到 `/config/services`，内联 `forwarder.nodes`。所有字段存入 `metadata`。 |
| `update_port_mapping(external_port, internal_port, internal_client, protocol, description, remote_host, enabled, lease_duration)` | PUT `/config/services/{name}` — 原地更新已有服务（刷新 `created_at` 延长租期）。AddPortMapping 同客户端覆盖场景使用。 |
| `delete_port_mapping(external_port, protocol)` | 直接构造名称为 `upnp_{port}_{protocol}`，DELETE `/config/services/{name}`。404 被静默吞掉。 |
| `get_port_mappings()` | 过滤出 `metadata.upnp == True` 的服务，所有字段从 metadata 读取（不解析 addr/forwarder）。 |
| `get_port_mapping_by_index(index)` | 从 `get_port_mappings()` 返回第 N 个映射，或 `None`。 |
| `has_port_mapping(external_port, protocol)` | 便捷检查——遍历映射查找匹配的端口+协议。 |
| `get_expired_services()` | 返回 `now >= created_at + lease_duration`（lease > 0）的服务列表。 |

## 命名规则

| 实体 | 格式 | 示例 |
|---|---|---|
| Service 名称 | `upnp_{port}_{protocol}` | `upnp_8080_tcp` |

没有单独的 chain 或 node 名称——forwarder 节点内联在 service 配置中。

## 元数据存储

AddPortMapping 的所有字段都存储在 GOST service 的 `metadata` 字典中：

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

`get_port_mappings()` 直接从 metadata 读取——不依赖 addr/handler/forwarder 解析。

## 重试行为

`_request()` 对 `ConnectionError` 和 `Timeout` 最多重试 2 次，使用指数退避（2^attempt 秒）。HTTP 错误和 JSON 解码错误立即抛出，不重试。

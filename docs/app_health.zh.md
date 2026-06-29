# app_health.py — 健康检查服务

封装 `/health` 端点逻辑：验证 GOST API 连通性并返回应用状态摘要。无 Flask 依赖。

## HealthService

### 构造参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `gost_client` | `GostClient` | 用于连通性检查的 GOST API 客户端。 |
| `version` | `str` | 应用版本字符串。 |
| `get_local_ip` | `Callable[[], str]` | 返回本地 IP 地址的函数。 |
| `get_local_port` | `Callable[[], int]` | 返回监听端口的函数。 |

### 方法

| 方法 | 返回值 | 说明 |
|---|---|---|
| `check()` | `dict[str, Any]` | 返回健康检查摘要 JSON。 |

### 响应格式

```json
{
  "status": "healthy | degraded",
  "version": "1.0.0",
  "local_ip": "192.168.1.1",
  "local_port": 5000,
  "gost_api": "http://127.0.0.1:8000",
  "gost_connected": true,
  "port_mappings_count": 5
}
```

GOST API 不可达时 `status` 为 `"degraded"`，否则为 `"healthy"`。

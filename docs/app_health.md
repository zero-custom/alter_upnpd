# app_health.py — Health Check Service

Encapsulates the `/health` endpoint logic: verifies GOST API connectivity and returns the application status summary. No Flask dependency.

## HealthService

### Constructor

| Param | Type | Description |
|---|---|---|
| `gost_client` | `GostClient` | GOST API client for connectivity check. |
| `version` | `str` | Application version string. |
| `get_local_ip` | `Callable[[], str]` | Function that returns the local IP address. |
| `get_local_port` | `Callable[[], int]` | Function that returns the listening port. |

### Methods

| Method | Returns | Description |
|---|---|---|
| `check()` | `dict[str, Any]` | Returns health summary JSON. |

### Response Format

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

`status` is `"degraded"` when GOST API is unreachable; `"healthy"` otherwise.

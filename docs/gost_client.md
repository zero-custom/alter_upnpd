# gost_client.py — GOST REST API Client

Wraps the GOST `/config/services` API for port mapping CRUD, metrics, and server health checks. Refactored into four separate seams for testability and single responsibility.

## Module Structure

```
GostTransport          — Low-level HTTP transport (auth, retry, timeout)
PortMappingRepository  — Port mapping CRUD + cache + expiry
GostMetricsClient      — Prometheus metrics discovery, fetching, parsing
GostClient             — Thin facade (backward-compatible)
SpeedTracker           — Per-service traffic speed calculation
PrometheusMetrics      — Parsed metrics snapshot object
```

## Error Handling

Typed exception classes instead of dict return values:

| Exception | When Raised |
|---|---|
| `GostConnectionError` | Connection/Timeout errors (retryable - 2 attempts, exponential backoff) |
| `GostApiError` | HTTP errors (4xx/5xx) and JSON decode errors (non-retryable) |

## `GostTransport`

Low-level HTTP transport. Handles authentication, retry, and timeout. Used by both `PortMappingRepository` and `GostMetricsClient`.

```python
transport = GostTransport(base_url, timeout=10, retries=2, username="", password="")
transport.request("GET", "/config/services")

# Connectivity check
transport.is_available()  # Pings /config/services with 5s timeout
```

## `PortMappingRepository`

Port mapping CRUD with service cache and expiry. Focused on one concern: reading and writing port mappings to the GOST API.

| Method | Description |
|---|---|
| `get_services()` | Fetches all services from GOST. Cached (30s TTL). Returns `[]` on failure. |
| `add_port_mapping(...)` | Single POST to `/config/services` with inline `forwarder.nodes`. |
| `update_port_mapping(...)` | PUT `/config/services/{name}` in-place update (refreshes `created_at`). |
| `delete_port_mapping(port, protocol)` | Direct name `upnp_{port}_{protocol}`, DELETE. 404 silently swallowed. |
| `get_port_mappings()` | Filter `metadata.upnp == True`, reads from metadata. |
| `get_port_mapping_by_index(index)` | Nth mapping or `None`. |
| `has_port_mapping(port, protocol)` | Iterates mappings for matching port+protocol. |
| `get_expired_services()` | Lists services where `now >= created_at + lease_duration`. |

## `GostMetricsClient`

Prometheus metrics discovery, fetching, and parsing. Independent seam — callers that only need metrics (e.g. webui stats) can inject this without the CRUD layer.

| Method | Description |
|---|---|
| `fetch_metrics()` | Fetches and parses Prometheus text. Returns `PrometheusMetrics` or `None`. |
| `discover_metrics_url()` | Auto-discovers metrics endpoint from GOST API root. |

## `GostClient` (Facade)

Thin facade combining `PortMappingRepository` and `GostMetricsClient`. Existing callers continue to work unchanged. New code can inject repository or metrics client directly.

## `SpeedTracker`

Per-service traffic speed calculation from byte counters, with configurable sliding window.

## `PrometheusMetrics`

Parsed Prometheus metrics snapshot. Provides typed accessors for gauge values.

## Naming Convention

| Entity | Format | Example |
|---|---|---|
| Service name | `upnp_{port}_{protocol}` | `upnp_8080_tcp` |

## Metadata Storage

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

## Retry Behaviour

`GostTransport._request()` retries `ConnectionError` and `Timeout` up to 2 times with exponential backoff. HTTP errors and JSON decode errors are raised immediately.

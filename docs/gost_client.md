# gost_client.py — GOST REST API Client

Wraps the GOST `/config/services` API for port mapping CRUD and server health checks.

## Error Handling

Uses typed exception classes instead of dict return values:

| Exception | When Raised |
|---|---|
| `GostConnectionError` | Connection/Timeout errors (retryable — 2 attempts, exponential backoff) |
| `GostApiError` | HTTP errors (4xx/5xx) and JSON decode errors (non-retryable) |

Callers use `try/except` blocks. `get_services()` and `is_available()` catch exceptions internally and return safe defaults.

## `GostClient`

Instance per application. Holds a TTL-less service cache (`_services_cache`) that is cleared on every write operation (add/delete).

## Methods

| Method | Description |
|---|---|
| `is_available()` | Pings `/config/services` with 5s timeout, returns `True`/`False`. |
| `get_services()` | Fetches all services from GOST. Cached. Returns `[]` on failure. Handles list, dict.data, and nested responses. |
| `add_port_mapping(external_port, internal_port, internal_client, protocol, description, remote_host, enabled, lease_duration)` | Single POST to `/config/services` with inline `forwarder.nodes`. Stores all fields in `metadata`. |
| `update_port_mapping(external_port, internal_port, internal_client, protocol, description, remote_host, enabled, lease_duration)` | PUT `/config/services/{name}` — updates an existing service in-place (refreshes `created_at` to extend lease). Used by same-client overwrite in AddPortMapping. |
| `delete_port_mapping(external_port, protocol)` | Direct name construction `upnp_{port}_{protocol}`, DELETEs from `/config/services/{name}`. 404s are silently swallowed. |
| `get_port_mappings()` | Filters services to those with `metadata.upnp == True`, reads all fields from metadata (not addr/forwarder parsing). |
| `get_port_mapping_by_index(index)` | Nth mapping from `get_port_mappings()`, or `None`. |
| `has_port_mapping(external_port, protocol)` | Convenience check — iterates mappings for matching port+protocol. |
| `get_expired_services()` | Returns list of services where `now >= created_at + lease_duration` (lease > 0). |

## Naming Convention

| Entity | Format | Example |
|---|---|---|
| Service name | `upnp_{port}_{protocol}` | `upnp_8080_tcp` |

No separate chain or node names — forwarder nodes are inlined in the service config.

## Metadata Storage

All AddPortMapping fields stored in the GOST service `metadata` dict:

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

`get_port_mappings()` reads exclusively from metadata — no addr/handler/forwarder parsing.

## Retry Behaviour

`_request()` retries `ConnectionError` and `Timeout` up to 2 times with exponential backoff (2^attempt seconds). HTTP errors and JSON decode errors are raised immediately without retry.

# config.py — Configuration

## Architecture

`config.py` is organized in three parts:

| Part | What | How to use |
|---|---|---|
| **PART 1: EnvConfig** | Environment-variable config (18 fields) | Constructed once via `load_env_config()` at app startup. Stays in `app.py` — individual values are passed to each module's constructor. |
| **PART 2: Grouped constants** | Hard-coded tunables, grouped by owning module | Import only your module's group: `from config import GostClientConfig` then `GostClientConfig.REQUEST_TIMEOUT` |
| **PART 3: Reference** | Constants defined in their own modules | Listed for discoverability only. Edit the source module to change. |

## Module groups (PART 2)

Each module imports its own group and uses constants directly:

```python
# gost_client.py
from config import GostClientConfig
# GostClientConfig.REQUEST_TIMEOUT  → 10
# GostClientConfig.RETRIES          → 2

# ssdp_responder.py
from config import SsdpConfig
# SsdpConfig.CACHE_CONTROL  → 1800
# SsdpConfig.SERVER_ID      → "Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0"

# stun_client.py
from config import StunConfig
# StunConfig.RETRIES             → 4
# StunConfig.REFRESH_INTERVAL    → 86400
# StunConfig.FALLBACK_WAN_IP     → "192.0.2.1"

# app.py
from config import AppConfig
# AppConfig.SHUTDOWN_TIMEOUT  → 5
# AppConfig.VERSION           → "1.2.0"
```

## Environment variables (PART 1)

| Variable | EnvConfig field | Default | Description |
|---|---|---|---|
| `GOST_API_URL` | `gost_api_url` | `http://127.0.0.1:8000` | Base URL of the GOST REST API. |
| `LISTEN_PORT` | `listen_port` | `5000` | Port the Flask HTTP server binds to. |
| `DEBUG` | `debug` | `false` | Enables debug-level logging. |
| `ACL_ENABLED` | `acl_enabled` | `true` | Enables IP-based access control for SOAP endpoints. |
| `SECURE_MODE` | `secure_mode` | `true` | Blocks AddPortMapping to a different IP than the requester; blocks DeletePortMapping of others' mappings. |
| `ACL_ALLOWED_SUBNETS` | `acl_allowed_subnets` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | Comma-separated CIDR subnets allowed to send SOAP requests. |
| `SSDP_NOTIFY_INTERVAL` | `ssdp_notify_interval` | `180` | Interval (seconds) between SSDP `ssdp:alive` NOTIFY multicast announcements. |
| `STUN` | `stun` | `true` | Enables STUN-based external IP discovery on startup. |
| `STUN_SERVER` | `stun_server` | `stun.l.google.com:19302` | STUN server host and port (for external IP discovery). |
| `LEASE_DURATION` | `lease_duration` | `604800` | Default lease duration (seconds) for port mappings. Capped at 604800 (7 days). |
| `LEASE_CLEANUP_INTERVAL` | `lease_cleanup_interval` | `60` | Interval (seconds) between expired lease cleanup scans. |
| `UPSTREAM_IGD_URL` | `upstream_igd_url` | `""` | rootDesc.xml URL of an upstream UPnP IGD. When set, AddPortMapping / DeletePortMapping are mirrored to the upstream IGD automatically (silent degradation on failure). |
| `UPSTREAM_INTERNAL_HOST` | `upstream_internal_host` | `""` | Override the `NewInternalClient` sent to the upstream IGD when mirroring port mappings. Empty = let upstream IGD auto-fill the SOAP source IP. |
| `GOST_API_USERNAME` | `gost_api_username` | `""` | Username for GOST API Basic Auth (both username and password must be set to take effect). |
| `GOST_API_PASSWORD` | `gost_api_password` | `""` | Password for GOST API Basic Auth. |
| `GOST_METRICS_URL` | `gost_metrics_url` | `""` | Prometheus metrics URL for real-time bandwidth/connection stats. Empty = auto-discovered from GOST API `/metrics` endpoint. |
| `GOST_WEBUI_REFRESH_INTERVAL` | `gost_webui_refresh_interval` | `10` | Dashboard refresh interval (seconds). |
| `GOST_WEBUI_HISTORY_POINTS` | `gost_webui_history_points` | `8640` | Max data points stored per port for traffic charts. |

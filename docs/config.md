# config.py — Configuration

Global configuration via environment variables. Exposed as class attributes on `Config`.

| Variable | Default | Description |
|---|---|---|
| `GOST_API_URL` | `http://127.0.0.1:8000` | Base URL of the GOST REST API. |
| `LISTEN_PORT` | `5000` | Port the Flask HTTP server binds to. |
| `DEBUG` | `false` | Enables debug-level logging. |
| `ACL_ENABLED` | `true` | Enables IP-based access control for SOAP endpoints. |
| `SECURE_MODE` | `true` | Blocks AddPortMapping to a different IP than the requester; blocks DeletePortMapping of others' mappings. |
| `ACL_ALLOWED_SUBNETS` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | Comma-separated CIDR subnets allowed to send SOAP requests. |
| `SSDP_NOTIFY_INTERVAL` | `180` | Interval (seconds) between SSDP `ssdp:alive` NOTIFY multicast announcements. |
| `STUN` | `true` | Enables STUN-based external IP discovery on startup. |
| `STUN_SERVER` | `stun.l.google.com:19302` | STUN server host and port (for external IP discovery). |
| `LEASE_DURATION` | `604800` | Default lease duration (seconds) for port mappings. Capped at 604800 (7 days). |
| `LEASE_CLEANUP_INTERVAL` | `60` | Interval (seconds) between expired lease cleanup scans. |
| `UPSTREAM_IGD_URL` | `""` | rootDesc.xml URL of an upstream UPnP IGD. When set, AddPortMapping / DeletePortMapping are mirrored to the upstream IGD automatically (silent degradation on failure). |
| `UPSTREAM_INTERNAL_HOST` | `""` | Override the `NewInternalClient` sent to the upstream IGD when mirroring port mappings. Empty = let upstream IGD auto-fill the SOAP source IP. |
| `GOST_API_USERNAME` | `""` | Username for GOST API Basic Auth (both username and password must be set to take effect). |
| `GOST_API_PASSWORD` | `""` | Password for GOST API Basic Auth. |
| `GOST_METRICS_URL` | `""` | Prometheus metrics URL for real-time bandwidth/connection stats. Empty = auto-discovered from GOST API `/metrics` endpoint. |
| `GOST_WEBUI_REFRESH_INTERVAL` | `10` | Dashboard refresh interval (seconds). |
| `GOST_WEBUI_HISTORY_POINTS` | `8640` | Max data points stored per port for traffic charts. |
| `GOST_REQUEST_TIMEOUT` | `10` | HTTP request timeout (seconds) for GOST API calls. |
| `GOST_RETRIES` | `2` | Number of retry attempts for GOST API connection/timeout errors (exponential backoff). |

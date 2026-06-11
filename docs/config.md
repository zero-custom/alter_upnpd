# config.py — Configuration

Global configuration via environment variables. Exposed as class attributes on `Config`.

| Variable | Default | Description |
|---|---|---|
| `GOST_API_URL` | `http://127.0.0.1:8000` | Base URL of the GOST REST API. |
| `LISTEN_PORT` | `8000` | Port the Flask HTTP server binds to. |
| `DEBUG` | `false` | Enables debug-level logging. |
| `ACL_ENABLED` | `true` | Enables IP-based access control for SOAP endpoints. |
| `ACL_ALLOWED_SUBNETS` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | Comma-separated CIDR subnets allowed to send SOAP requests. |
| `SSDP_NOTIFY_INTERVAL` | `180` | Interval (seconds) between SSDP `ssdp:alive` NOTIFY multicast announcements. |
| `STUN` | `true` | Enables STUN-based external IP discovery on startup. |
| `STUN_SERVER` | `stun.l.google.com:19302` | STUN server host and port (for external IP discovery). |
| `LEASE_DURATION` | `604800` | Default lease duration (seconds) for port mappings. Capped at 604800 (7 days). |
| `LEASE_CLEANUP_INTERVAL` | `60` | Interval (seconds) between expired lease cleanup scans. |

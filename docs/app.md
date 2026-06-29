# app.py — Flask Application & Entrypoint

Main Flask application. Defines HTTP routes, template rendering, background service lifecycle, and the `main()` entrypoint. Health check and lifecycle management have been extracted into separate modules (`app_health.py`, `lifecycle.py`).

## Routes

| Path | Method | Description |
|---|---|---|
| `/rootDesc.xml` | GET | Root device description XML (Jinja2 with `LOCAL_IP`, `LOCAL_PORT`). |
| `/L3F.xml` | GET | Layer3Forwarding SCPD. |
| `/WANCfg.xml` | GET | WANCommonInterfaceConfig SCPD. |
| `/WANIPCn.xml` | GET | WANIPConnection SCPD. |
| `/ctl/L3F` | POST | Layer3Forwarding SOAP actions. |
| `/ctl/CmnIfCfg` | POST | WANCommonInterfaceConfig SOAP actions. |
| `/ctl/IPConn` | POST | WANIPConnection SOAP actions (primary). |
| `/ctl/WANIPCn` | POST | WANIPConnection SOAP actions (alias). |
| `/ctl/WANPPPCn` | POST | WANPPPConnection SOAP actions (same handler as IPConn). |
| `/` | GET/POST | WebUI dashboard (PyWebIO via `webio_view`). |
| `/health` | GET | JSON health check (via `HealthService`). |
| `/static/<path>` | GET | Local static assets (ECharts JS, via `static_bp`). |

Any `*.xml` path not listed above is handled by the catch-all `/<path:filename>` route, rendering the matching XML template from `xml/`.

## Template Rendering

XML templates are loaded from `app/xml/` using Jinja2 via `TemplateRenderer` (`template.py`) and cached with mtime-based invalidation. Only `rootDesc.xml` uses template variables; SCPD files are static but rendered through Jinja2.

## Helper Functions

| Function | Description |
|---|---|
| `get_local_ip()` | Discovers local IP via `socket.connect()` to `10.255.255.255:1`. Falls back to `127.0.0.1`. |
| `get_local_port()` | Returns `Config.LISTEN_PORT`. |
| `get_location()` | Returns `http://{ip}:{port}/rootDesc.xml`. |

## Background Services

Initiated via `AppLifecycle.start()` (`lifecycle.py`), launched on application startup:

| Service | Module | Description |
|---|---|---|
| SSDP responder | `ssdp_responder.py` | Sends periodic `ssdp:alive` NOTIFY announcements (every `Config.SSDP_NOTIFY_INTERVAL` sec). |
| Lease cleanup | `lifecycle.py` | Scans all services for expired leases (every `Config.LEASE_CLEANUP_INTERVAL` sec), deletes expired ones. |
| STUN client | `stun_client.py` | If `Config.STUN` is enabled, starts STUN refresh thread for external IP discovery. |

`AppLifecycle.stop()` sends SSDP `ssdp:byebye` notifications and joins the SSDP thread.

## Health Check

`GET /health` implemented via `HealthService` (`app_health.py`). Returns JSON with:
- `status`: `"healthy"` or `"degraded"` (based on GOST API connectivity)
- `gost_connected`: boolean
- `port_mappings_count`: integer
- `local_ip`, `local_port`, `gost_api`, `version`

## Entrypoint

`main()` — Direct Python execution: calls `setup_logging()`, configures signal handlers, creates `AppLifecycle` and calls `start()`, runs the Flask dev server on `0.0.0.0:{LISTEN_PORT}`, and `AppLifecycle.stop()` on exit.

## WSGI

`application = app` at module level for gunicorn / uvicorn ASGI-wrapped serving. See `gunicorn_config.py`.

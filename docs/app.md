# app.py — Flask Application & Entrypoint

Main Flask application. Defines HTTP routes, template rendering, background service lifecycle, and the `main()` entrypoint.

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
| `/` | GET | Status page with IP:port. |
| `/health` | GET | JSON health check (local IP, port, GOST API URL, GOST connectivity, mapping count, version). |

Any `*.xml` path not listed above is handled by the catch-all `/<path:filename>` route, rendering the matching XML template from `xml/`.

## Template Rendering

XML templates are loaded from `app/xml/` using Jinja2 and cached with mtime-based invalidation (`TEMPLATE_CACHE`). Only `rootDesc.xml` uses template variables; SCPD files are static but rendered through Jinja2.

## Helper Functions

| Function | Description |
|---|---|
| `get_local_ip()` | Discovers local IP via `socket.connect()` to `10.255.255.255:1`. Falls back to `127.0.0.1`. |
| `get_local_port()` | Returns `Config.LISTEN_PORT`. |
| `get_location()` | Returns `http://{ip}:{port}/rootDesc.xml`. |

## Background Services

`init_background_services()` starts on application launch:

| Service | Description |
|---|---|
| SSDP responder | Sends periodic `ssdp:alive` NOTIFY announcements (every `Config.SSDP_NOTIFY_INTERVAL` sec). |
| Lease cleanup | Scans all services for expired leases (every `Config.LEASE_CLEANUP_INTERVAL` sec), deletes expired ones. |
| STUN client | If `Config.STUN` is enabled, starts STUN refresh thread for external IP discovery. |

`shutdown_background_services()` sends SSDP `ssdp:byebye` notifications and joins the SSDP thread.

## Entrypoint

`main()` — Direct Python execution: calls `setup_logging()`, configures signal handlers, calls `init_background_services()`, runs the Flask dev server on `0.0.0.0:{LISTEN_PORT}`, and `shutdown_background_services()` on exit.

## Health Check

`GET /health` returns JSON with:
- `status`: `"healthy"` or `"degraded"` (based on GOST API connectivity)
- `gost_connected`: boolean
- `port_mappings_count`: integer
- `local_ip`, `local_port`, `gost_api`, `version`

## WSGI

`application = app` at module level for gunicorn / uvicorn ASGI-wrapped serving. See `gunicorn_config.py`.

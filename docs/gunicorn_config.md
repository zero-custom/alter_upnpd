# gunicorn_config.py — Gunicorn WSGI Configuration

Gunicorn server configuration for production deployment. Single worker, synchronous mode.

| Setting | Value |
|---|---|
| `bind` | `0.0.0.0:{LISTEN_PORT}` (from environment, default 5000) |
| `workers` | 1 |
| `worker_class` | `sync` |
| `timeout` | 30s |
| `graceful_timeout` | 10s |
| `keepalive` | 5s |

## Lifecycle Hooks

| Hook | Action |
|---|---|
| `on_starting` | Calls `app.setup_logging()` to configure logging. |
| `post_worker_init` | Calls `app.init_background_services()` to start SSDP, STUN, and lease-cleanup threads. |
| `worker_exit` | Calls `app.shutdown_background_services()` to SSDP byebye and join threads. |

## Why Single Worker

UPnP IGD state (SSDP sockets, STUN thread) is per-process. Multiple workers would each try to bind SSDP multicast sockets (only one succeeds) and duplicate periodic tasks. Single worker with `sync` mode is the correct deployment model.

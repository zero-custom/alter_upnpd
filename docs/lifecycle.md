# lifecycle.py — Background Service Lifecycle

Manages the startup and shutdown of background services: STUN resolution, SSDP responder, and lease cleanup thread.

## AppLifecycle

### Constructor

| Param | Description |
|---|---|
| `gost_client` | GOST API client (passed to lease cleanup). |
| `get_location_fn` | Returns the device location URL (`http://{ip}:{port}/rootDesc.xml`). |
| `ssdp_notify_interval` | Seconds between SSDP NOTIFY announcements. |
| `lease_cleanup_interval` | Seconds between lease cleanup scans. |
| `acl_enabled` | Whether ACL is enabled (logged at startup). |
| `acl_allowed_subnets` | Allowed subnets string (logged at startup). |
| `version` | Application version string (logged at startup). |
| `stun_client` | `StunClient \| None` — STUN client instance. `None` when STUN is disabled. |
| `upstream_client` | `UpstreamClient \| None` — upstream IGD client for reconcile. `None` when upstream sync is not configured. |
| `shutdown_timeout` | Max seconds to wait for SSDP thread on shutdown. |

### Methods

| Method | Returns | Description |
|---|---|---|
| `shutdown_event` (property) | `threading.Event` or `None` | The shutdown event used to signal background threads. `None` before `start()` is called. |
| `start()` | `threading.Event` | Starts STUN, SSDP, and lease cleanup threads. Returns the shutdown event. |
| `stop()` | `None` | Signals shutdown, sends SSDP byebye, joins threads. |

### Threads

| Thread | Name | Daemon | Function |
|---|---|---|---|
| STUN | — | Yes | Runs `StunClient._refresh_loop()`. Started inside `start()` via `StunClient.start()`. Daemon, auto-exits on process exit. |
| SSDP responder | `ssdp` | No | Runs `asyncio.run(SSDPResponder.start())`. Joined on stop for clean byebye. |
| Lease cleanup | `lease-cleanup` | Yes | Polls `GostClient.get_expired_services()`, deletes expired mappings. Then calls `UpstreamClient.reconcile()` with current GOST mappings to restore any missing upstream IGD entries. Sleeps `lease_cleanup_interval` seconds. |

### Startup Flow

1. Logs version, device location, GOST API URL, ACL status.
2. Starts STUN client (if configured):
   - Spawns a daemon thread that immediately performs the first STUN resolution, then refreshes every 24h.
   - Waits up to 10 seconds via `wait_ready()` for the first resolution to complete.
   - If STUN times out, logs a warning and continues — the refresh loop will retry.
3. Creates `threading.Event` for shutdown signalling.
4. Starts SSDP responder thread.
5. Starts lease cleanup daemon thread.
6. Returns the shutdown event.

### Shutdown Flow

1. Sets the shutdown event.
2. Sends SSDP `ssdp:byebye` via `SSDPResponder`.
3. Waits for SSDP thread to finish (up to `shutdown_timeout` seconds).

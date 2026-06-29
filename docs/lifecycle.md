# lifecycle.py — Background Service Lifecycle

Manages the startup and shutdown of background services: SSDP responder and lease cleanup thread.

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
| `shutdown_timeout` | Max seconds to wait for SSDP thread on shutdown. |

### Methods

| Method | Returns | Description |
|---|---|---|
| `shutdown_event` (property) | `threading.Event` or `None` | The shutdown event used to signal background threads. |
| `start()` | `threading.Event` | Starts SSDP and lease cleanup threads. Returns the shutdown event. |
| `stop()` | `None` | Signals shutdown, sends SSDP byebye, joins threads. |

### Threads

| Thread | Name | Daemon | Function |
|---|---|---|---|
| SSDP responder | `ssdp` | No | Runs `asyncio.run(SSDPResponder.start())`. Joined on stop. |
| Lease cleanup | `lease-cleanup` | Yes | Polls `GostClient.get_expired_services()`, deletes expired, sleeps. |

### Startup Flow

1. Logs version, device location, GOST API URL, ACL status.
2. Creates `threading.Event` for shutdown signalling.
3. Starts SSDP responder thread.
4. Starts lease cleanup daemon thread.
5. Returns the shutdown event.

### Shutdown Flow

1. Sets the shutdown event.
2. Sends SSDP `ssdp:byebye` via `SSDPResponder`.
3. Waits for SSDP thread to finish (up to `shutdown_timeout` seconds).

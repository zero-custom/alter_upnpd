# stun_client.py — STUN External IP Resolution

Discovers the WAN (external) IP address via STUN. Provides a background daemon thread that resolves the IP on startup via `AppLifecycle` and refreshes every 24 hours.

## Class: `StunClient`

### Constructor

| Param | Default | Description |
|---|---|---|
| `stun_server` | `"stun.l.google.com:19302"` | STUN server host:port. |
| `retries` | `4` | Max retries per refresh cycle. |
| `refresh_interval` | `86400` | Seconds between refreshes (24h). |
| `fallback_wan_ip` | `"192.0.2.1"` | IP returned when STUN resolution fails. |

### Methods

| Method | Returns | Description |
|---|---|---|
| `start()` | `None` | Starts the background refresh daemon thread. Idempotent. Clears the ready event. Called from `AppLifecycle.start()`. |
| `get_wan_ip()` | `str` | Returns the most recently discovered external IP. Thread-safe. Returns fallback `192.0.2.1` before first successful resolution. |
| `wait_ready(timeout=10.0)` | `bool` | Blocks until the first STUN refresh completes. Returns `True` if ready, `False` on timeout. |
| `reset_cache()` | `None` | Resets WAN IP to fallback and clears the ready event. For testing only. |

### Refresh Flow

1. Resolve STUN server hostname and port from `stun_server`.
2. Call `py3stun.get_ip_info()` with up to `retries` retries.
3. On success: store the external IP under a lock, log result, set the ready event.
4. On failure (all retries exhausted): keep the previous value (or fallback), log warning.
5. Sleep `refresh_interval` (86400s = 24h), then repeat from step 2.

## Integration with AppLifecycle

`AppLifecycle.start()` calls `stun_client.start()` then waits up to 10s via `wait_ready()` before starting SSDP. This ensures the initial WAN IP is resolved before UPnP clients can discover the device — preventing clients from receiving the fallback IP `192.0.2.1`.

## Integration with SOAP Handler

`GetExternalIPAddress` SOAP action calls `stun_client.get_wan_ip()` when STUN is enabled. When disabled (`STUN=false`), `stun_client` is `None` and the handler returns `192.0.2.1`.

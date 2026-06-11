# stun_client.py — STUN External IP Resolution

Discovers the WAN (external) IP address via STUN. Module-level functions (not a class). Provides a background thread that resolves the IP on startup and refreshes every 24 hours.

## Functions

### `init()`

Starts the background refresh daemon thread. Idempotent — subsequent calls are no-ops. Called from `app.init_background_services()` when `Config.STUN` is enabled.

### `get_wan_ip() -> str`

Returns the most recently discovered external IP. Thread-safe (protected by a lock). Fallback value is `1.2.3.4`.

### `reset_cache()`

Resets the WAN IP back to `1.2.3.4` and allows `init()` to start a new thread. Used for testing.

## Refresh Flow

1. Resolve STUN server hostname from `Config.STUN_SERVER` (format `host:port`).
2. Call `py3stun.get_ip_info()` with up to `_STUN_RETRIES` (4) retries.
3. On success: store the external IP, log result.
4. On failure (all retries exhausted): keep the previous value, log warning.
5. Sleep `_REFRESH_INTERVAL` (86400s = 24h), then repeat from step 2.

## Integration with SOAP Handler

`GetExternalIPAddress` SOAP action calls `stun_client.get_wan_ip()` when `Config.STUN` is enabled. When disabled, it returns the static fallback `1.2.3.4`.

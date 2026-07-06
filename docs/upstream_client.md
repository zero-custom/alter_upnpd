# upstream_client.py — Upstream IGD Port Mapping Sync

Forwards port mapping operations to an upstream UPnP IGD via miniupnpc, enabling port mapping propagation through double-NAT setups.

## Topology

```
upstream IGD:  ext:8888 ──►  (SOAP request source IP) :8888
GOST:          :8888    ──►  client_ip:9000
```

`NewInternalClient` is deliberately left empty — the upstream IGD (99% miniupnpd) fills it with the SOAP request source IP via its `#ifndef UPNP_STRICT` fallback. This avoids any dependency on local IP detection (socket / `u.lanaddr`).

## Call Flow

`UPSTREAM_IGD_URL` is checked at the **caller** (`upnp_soap.py`), not inside this module:

```
upnp_soap.py:
    if EnvConfig.upstream_igd_url:
        upstream_client.add_port_mapping(...)
```

This module is a pure executor — it does not decide whether forwarding should happen.

## Configuration

| Env Var | Default | Description |
|---|---|---|
| `UPSTREAM_IGD_URL` | `""` | Upstream IGD rootDesc.xml URL. Empty = disabled. |
| `UPSTREAM_INTERNAL_HOST` | `""` | Override `NewInternalClient` sent to upstream IGD. Empty = let upstream IGD auto-fill the SOAP source IP. |

## Functions

| Function | Visibility | Description |
|---|---|---|
| `add_port_mapping(...)` | Public | Forward AddPortMapping to upstream IGD. Lazy-init on first call. Non-blocking on failure. |
| `delete_port_mapping(...)` | Public | Forward DeletePortMapping to upstream IGD. Lazy-init on first call. Non-blocking on failure. |
| `_ensure_upnp()` | Private | Lazy initializer: creates miniupnpc client, connects to `UPSTREAM_IGD_URL`. Called automatically on first `add_port_mapping` / `delete_port_mapping`. |
| `_ensure_upnp_connected()` | Private | Connection health check. Calls `getportmappingnumberofentries()` as heartbeat; if stale, destroys the old connection and re-runs `_ensure_upnp()`. Returns `bool`. |
| `list_mappings()` | Public | Enumerate all port mappings on the upstream IGD via `getgenericportmapping(i)` loop. Returns `list[dict]`. For debug/audit only — not used in production path. |
| `reconcile(gost_mappings)` | Public | Compare each GOST-managed mapping against the upstream IGD and restore missing ones. Returns `(restored, failed)`. See Reconcile Flow below. |

## Reconcile Flow

Reconcile addresses the upstream IGD mapping loss scenario (e.g., IGD restart). It runs inside the lease cleanup thread every `LEASE_CLEANUP_INTERVAL` (default 60s).

### Strategy: Approach B (on-demand query)

```
for each GOST mapping:
    getspecificportmapping(ext_port, proto)
    → None?      → addportmapping(...)   # missing → restore
    → returns tuple? → continue           # already exists
```

### Connection Health

```
reconcile()
  → _ensure_upnp_connected()
      → self._upnp exists?
          → getportmappingnumberofentries()     # heartbeat SOAP
              ✓ → return True
              ✗ → self._upnp = None, fall through
      → _ensure_upnp()                          # re-selectigd
          → miniupnpc.UPnP()
          → selectigd(self._igd_url)            # HTTP GET rootDesc.xml, no SSDP
          ✓ → self._upnp = u
          ✗ → self._upnp stays None → reconcile returns (0, 0)
```

- `selectigd(url)` calls `UPNP_GetIGDFromUrl()` — direct HTTP GET, never SSDP `upnpDiscover()`
- If the heartbeat fails, the old connection is destroyed and a new one established via the configured `UPSTREAM_IGD_URL`
- If reconnection fails, reconcile silently returns (0, 0) and retries next cycle

### Failure Isolation

| Failure | Impact |
|---|---|
| Heartbeat `getportmappingnumberofentries()` fails | Connection re-established; if reconnection also fails, reconcile skipped for this cycle |
| Individual `getspecificportmapping()` fails | Single mapping marked as `failed`, continues to next |
| Individual `addportmapping()` fails | Single mapping marked as `failed`, continues to next |

## Behavior

- **Lazy initialization**: miniupnpc client is created on the first actual port mapping call, not at import or startup time.
- **Silent degradation**: Upstream failures are logged as warnings; GOST-side mappings are unaffected.
- **NewInternalClient**: Left empty by default. The upstream IGD (miniupnpd default build) fills the SOAP request source IP — which is the alter_upnpd host. Set `UPSTREAM_INTERNAL_HOST` to override the `NewInternalClient` value when a different internal host is needed.
- **Port mapping symmetry**: The upstream mapping uses the same external port as the GOST mapping.
- **Reconnection**: Only `reconcile()` proactively detects stale connections and triggers reconnection. `add_port_mapping()` / `delete_port_mapping()` log failures but do not trigger reconnection themselves — they rely on the next reconcile cycle to restore connectivity.

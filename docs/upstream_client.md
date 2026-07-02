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

## Behavior

- **Lazy initialization**: miniupnpc client is created on the first actual port mapping call, not at import or startup time.
- **Silent degradation**: Upstream failures are logged as warnings; GOST-side mappings are unaffected.
- **NewInternalClient**: Left empty by default. The upstream IGD (miniupnpd default build) fills the SOAP request source IP — which is the alter_upnpd host. Set `UPSTREAM_INTERNAL_HOST` to override the `NewInternalClient` value when a different internal host is needed.
- **Port mapping symmetry**: The upstream mapping uses the same external port as the GOST mapping.

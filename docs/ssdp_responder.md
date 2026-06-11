# ssdp_responder.py — SSDP Discovery Protocol

Handles UPnP device discovery over SSDP (Simple Service Discovery Protocol): periodic multicast NOTIFY announcements for the root device.

## `SSDPResponder`

Creates UDP datagram endpoints on all non-loopback IPv4 interfaces and periodically sends `ssdp:alive` NOTIFY messages. Uses the `ssdp` library (`ssdp.aio.SimpleServiceDiscoveryProtocol`).

### Periodic NOTIFY `ssdp:alive`

Every 30 seconds, sends a multicast NOTIFY for `upnp:rootdevice`:

| Header | Value |
|---|---|
| `HOST` | `239.255.250.250:1900` |
| `NT` | `upnp:rootdevice` |
| `NTS` | `ssdp:alive` |
| `USN` | `uuid:ed8d683a-91ea-402b-9c25-d0a48f23e9d7::upnp:rootdevice` |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `CACHE-CONTROL` | `max-age=1800` |
| `SERVER` | `Linux/2.6.18 UPnP/1.0 alter_upnpd/1.0` |

### M-SEARCH Handling

`SSDPHandler` extends `aio.SimpleServiceDiscoveryProtocol`. The current implementation has stub methods (`response_received`, `request_received`, `_send_response`) that are effectively no-ops. M-SEARCH responses are not implemented.

## Startup Flow

1. Enumerate non-loopback IPv4 interfaces via `netifaces`.
2. For each interface, create a UDP datagram endpoint with `SSDPHandler` as the protocol.
3. Enter a loop: sleep 30 seconds, then send one `ssdp:alive` NOTIFY per interface.

## Failure Modes

- **PermissionError**: Cannot bind to privileged port (unlikely — uses ephemeral ports). If SSDP fails on an interface, it logs and continues with the remaining interfaces.
- **No non-loopback interfaces**: No SSDP notifications are sent.

# ssdp_responder.py — SSDP Discovery Protocol

Handles UPnP device discovery over SSDP (Simple Service Discovery Protocol): periodic multicast NOTIFY announcements and M-SEARCH responses.

## Module Constants

`UPNP_NT_LIST` — Centralised list of 8 UPnP device and service types, used by both `SSDPResponder` (NOTIFY alive/byebye) and `SSDPHandler` (M-SEARCH response). Adding or removing a UPnP service requires changing only this constant.

| # | NT | USN suffix |
|---|----|-----------|
| 1 | `upnp:rootdevice` | `::upnp:rootdevice` |
| 2 | `urn:schemas-upnp-org:device:InternetGatewayDevice:1` | `::urn:...:InternetGatewayDevice:1` |
| 3 | `urn:schemas-upnp-org:device:WANDevice:1` | `::urn:...:WANDevice:1` |
| 4 | `urn:schemas-upnp-org:device:WANConnectionDevice:1` | `::urn:...:WANConnectionDevice:1` |
| 5 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` | `::urn:...:Layer3Forwarding:1` |
| 6 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` | `::urn:...:WANCommonInterfaceConfig:1` |
| 7 | `urn:schemas-upnp-org:service:WANIPConnection:1` | `::urn:...:WANIPConnection:1` |
| 8 | `urn:schemas-upnp-org:service:WANPPPConnection:1` | `::urn:...:WANPPPConnection:1` |

## SSDPResponder

Creates UDP datagram endpoints on all non-loopback IPv4 interfaces, joins the SSDP multicast group, and periodically sends `ssdp:alive` NOTIFY messages. Uses the `ssdp` library (`ssdp.aio.SimpleServiceDiscoveryProtocol`).

### Periodic NOTIFY `ssdp:alive`

Every `EnvConfig.ssdp_notify_interval` seconds (default 180s), `_send_alive()` iterates over `UPNP_NT_LIST` and sends one NOTIFY per entry. Each NT gets its own try/except block — a failure on one entry does not prevent the others from being sent.

Each NOTIFY includes these headers:

| Header | Value |
|---|---|
| `HOST` | `239.255.255.250:1900` |
| `NT` | (from `UPNP_NT_LIST`) |
| `NTS` | `ssdp:alive` |
| `USN` | Derived from the NT entry |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `CACHE-CONTROL` | `max-age=1800` |
| `SERVER` | `Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0` |
| `BOOTID.UPNP.ORG` | Timestamp-based boot ID (changes on restart) |
| `CONFIGID.UPNP.ORG` | `1` (static — no runtime config changes) |

On shutdown, `_send_byebye()` sends all 8 messages with `NTS: ssdp:byebye`.

### M-SEARCH Handling

`SSDPHandler` extends `aio.SimpleServiceDiscoveryProtocol`. The ST→USN mapping (`_ST_USN_MAP`) is derived from `UPNP_NT_LIST` via dict comprehension.

1. `request_received()` parses the `ST` (Search Target) header.
2. Looks up the mapped USN in `_ST_USN_MAP` (8 device/service types + `ssdp:all`).
3. Calls `_send_search_response()` to reply.

**Matching logic:**

| Request `ST` | Response behavior |
|---|---|
| Specific type (e.g. `upnp:rootdevice`, `urn:...:WANIPConnection:1`) | Single 200 OK response with matched USN |
| `ssdp:all` | 8 responses, one for each device/service type |

### Device Lifecycle Identifiers

| Identifier | Value | Description |
|---|---|---|
| `BOOT_ID` | `int(time.time())` | Updated on every restart. Used in `BOOTID.UPNP.ORG` header. |
| `CONFIG_ID` | `1` | Static — no runtime config changes. |

### Startup Flow

1. Enumerate non-loopback IPv4 interfaces via `/sys/class/net/` (ioctl).
2. For each interface, create a UDP datagram endpoint with `SSDPHandler` as the protocol.
3. Send initial `ssdp:alive` NOTIFY burst.
4. Enter a loop: sleep 1 second, check if `notify_interval` has elapsed, send NOTIFY if so.

### Failure Modes

- **PermissionError**: Cannot bind to port 1900 – requires `CAP_NET_BIND_SERVICE` or root. Logs warning and continues without SSDP on that interface.
- **No non-loopback interfaces**: No SSDP notifications are sent.
- **Multicast join failure**: Logs warning but socket still works for sending.

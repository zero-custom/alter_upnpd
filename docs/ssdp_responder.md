# ssdp_responder.py — SSDP Discovery Protocol

Handles UPnP device discovery over SSDP (Simple Service Discovery Protocol): periodic multicast NOTIFY announcements and M-SEARCH responses.

## SSDPResponder

Creates UDP datagram endpoints on all non-loopback IPv4 interfaces, joins the SSDP multicast group, and periodically sends `ssdp:alive` NOTIFY messages. Uses the `ssdp` library (`ssdp.aio.SimpleServiceDiscoveryProtocol`).

### Periodic NOTIFY `ssdp:alive`

Every `Config.SSDP_NOTIFY_INTERVAL` seconds (default 180s), sends 8 NOTIFY messages across all interfaces:

| # | NT | USN |
|---|----|-----|
| 1 | `upnp:rootdevice` | `uuid:...::upnp:rootdevice` |
| 2 | `urn:schemas-upnp-org:device:InternetGatewayDevice:1` | `uuid:...::urn:...:InternetGatewayDevice:1` |
| 3 | `urn:schemas-upnp-org:device:WANDevice:1` | `uuid:...::urn:...:WANDevice:1` |
| 4 | `urn:schemas-upnp-org:device:WANConnectionDevice:1` | `uuid:...::urn:...:WANConnectionDevice:1` |
| 5 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` | `uuid:...::urn:...:Layer3Forwarding:1` |
| 6 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` | `uuid:...::urn:...:WANCommonInterfaceConfig:1` |
| 7 | `urn:schemas-upnp-org:service:WANIPConnection:1` | `uuid:...::urn:...:WANIPConnection:1` |
| 8 | `urn:schemas-upnp-org:service:WANPPPConnection:1` | `uuid:...::urn:...:WANPPPConnection:1` |

Each NOTIFY includes these headers:

| Header | Value |
|---|---|
| `HOST` | `239.255.255.250:1900` |
| `NT` | (varies per message — see table above) |
| `NTS` | `ssdp:alive` |
| `USN` | (varies per message) |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `CACHE-CONTROL` | `max-age=1800` |
| `SERVER` | `Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0` |
| `BOOTID.UPNP.ORG` | Timestamp-based boot ID (changes on restart) |
| `CONFIGID.UPNP.ORG` | `1` (static — no runtime config changes) |

On shutdown, `_send_byebye()` sends all 8 messages with `NTS: ssdp:byebye`.

### M-SEARCH Handling

`SSDPHandler` extends `aio.SimpleServiceDiscoveryProtocol`. M-SEARCH requests are fully handled:

1. `request_received()` parses the `ST` (Search Target) header.
2. Looks up the mapped USN in `_ST_USN_MAP` (8 device/service types + `ssdp:all`).
3. Calls `_send_search_response()` to reply.

**Matching logic:**

| Request `ST` | Response behavior |
|---|---|
| Specific type (e.g. `upnp:rootdevice`, `urn:...:WANIPConnection:1`) | Single 200 OK response with matched USN |
| `ssdp:all` | 8 responses, one for each device/service type |

Each M-SEARCH response includes:

| Header | Value |
|---|---|
| `CACHE-CONTROL` | `max-age=1800` |
| `DATE` | Current time in RFC 1123 format |
| `LOCATION` | `http://{ip}:{port}/rootDesc.xml` |
| `SERVER` | `Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0` |
| `ST` | Echoes the request's `ST` value |
| `USN` | Matched USN from the map |
| `EXT` | (empty) |
| `BOOTID.UPNP.ORG` | Boot ID |
| `CONFIGID.UPNP.ORG` | `1` |

### Device Lifecycle Identifiers

| Identifier | Value | Description |
|---|---|---|
| `BOOT_ID` | `int(time.time())` | Updated on every restart. Used in `BOOTID.UPNP.ORG` header. |
| `CONFIG_ID` | `1` | Static — no runtime config changes. Used in `CONFIGID.UPNP.ORG` header. |

### Startup Flow

1. Enumerate non-loopback IPv4 interfaces via `/sys/class/net/` (ioctl).
2. For each interface, create a UDP datagram endpoint with `SSDPHandler` as the protocol.
3. Send initial `ssdp:alive` NOTIFY burst.
4. Enter a loop: sleep 1 second, check if `notify_interval` has elapsed, send NOTIFY if so.

### Failure Modes

- **PermissionError**: Cannot bind to port 1900 – requires `CAP_NET_BIND_SERVICE` or root. Logs warning and continues without SSDP on that interface.
- **No non-loopback interfaces**: No SSDP notifications are sent.
- **Multicast join failure**: Logs warning but socket still works for sending.

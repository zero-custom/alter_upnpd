# upnp_soap.py — UPnP SOAP Action Handler

Parses incoming SOAP requests, dispatches to the correct action handler, and builds SOAP XML responses for the WANIPConnection:1, WANCommonInterfaceConfig:1, and Layer3Forwarding:1 services.

## Service Architecture

Three action registries (plain dicts) map action names to handler methods:

| Registry | Service | Default URN |
|---|---|---|
| `SOAP_ACTIONS` | WANIPConnection:1 | `urn:schemas-upnp-org:service:WANIPConnection:1` |
| `CIC_ACTIONS` | WANCommonInterfaceConfig:1 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` |
| `L3F_ACTIONS` | Layer3Forwarding:1 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` |

Actions are registered via `@soap_action`, `@cic_action`, or `@l3f_action` decorators.

## `UPnPSOAPHandler`

### Dispatchers

| Method | Registry | Routes bound in `app.py` |
|---|---|---|
| `handle_wanipconnection()` | `SOAP_ACTIONS` | `/ctl/IPConn`, `/ctl/WANIPCn`, `/ctl/WANPPPCn` |
| `handle_wancommonifconfig()` | `CIC_ACTIONS` | `/ctl/CmnIfCfg` |
| `handle_l3forwarding()` | `L3F_ACTIONS` | `/ctl/L3F` |

All dispatchers share `_handle_service_request()` which:
1. Checks ACL (if `Config.ACL_ENABLED`) — blocks IPs not in `Config.ACL_ALLOWED_SUBNETS`.
2. Reads the raw SOAP XML body from the Flask request.
3. Parses via `parse_soap_body()` to extract action name and parameters.
4. Sniffs the `SOAPAction` header to determine the action name (falls back to parsed body action).
5. Looks up the handler in the registry and calls it with parsed parameters.
6. Returns the handler's XML response as a Flask `Response`.

### SOAP Action Handlers (WANIPConnection:1)

| Action | Description |
|---|---|
| `AddPortMapping` | Creates a GOST port mapping. Captures `NewRemoteHost` and `NewEnabled` in addition to standard UPnP fields. Checks `has_port_mapping()` to detect conflicts (error 716). Calls `gost.add_port_mapping()` with all parameters. |
| `DeletePortMapping` | Deletes a GOST port mapping by constructing service name `upnp_{external_port}_{protocol}`. Calls `gost.delete_port_mapping()`. |
| `GetGenericPortMappingEntry` | Returns the Nth mapping (index-based pagination via `get_port_mapping_by_index`). Includes `lease_duration_remaining`. |
| `GetSpecificPortMappingEntry` | Returns mapping matching external port + protocol + remote host from `get_port_mappings()`. |
| `GetPortMappingNumberOfEntries` | Returns the total count of UPnP mappings. |
| `GetExternalIPAddress` | Returns STUN-discovered IP when `Config.STUN` is enabled, otherwise `1.2.3.4`. |
| `GetConnectionTypeInfo` | Returns `IP_Routed` (static). |
| `GetLinkLayerMaxBitRates` | Returns 0 (static). |
| `GetStatusInfo` | Returns `Connected`, `ERROR_NONE`, and uptime. |
| `GetNATRSIPStatus` | Returns RSIP unavailable, NAT enabled. |
| `SetConnectionType` | Returns fault 606 (Action not authorized). |
| `RequestConnection` | Returns fault 606 (Action not authorized). |
| `ForceTermination` | Returns fault 606 (Action not authorized). |

### WANCommonInterfaceConfig Handlers

| Action | Description |
|---|---|
| `GetCommonLinkProperties` | Static: Ethernet, 0 bitrates, Up. |
| `GetTotalBytesSent` | Returns 0. |
| `GetTotalBytesReceived` | Returns 0. |
| `GetTotalPacketsSent` | Returns 0. |
| `GetTotalPacketsReceived` | Returns 0. |

### Layer3Forwarding Handlers

| Action | Description |
|---|---|
| `GetDefaultConnectionService` | Returns `urn:upnp-org:serviceId:WANIPConn1`. |
| `SetDefaultConnectionService` | Empty success. |

## Namespace Handling

`build_soap_response()` accepts an optional `service_urn` parameter that defaults to the last set `_current_service_urn`. WANIPConnection and WANPPPConnection requests both hit `handle_wanipconnection()`.

## Error Handling

SOAP faults use UPnP error codes wrapped in a `<s:Fault>` envelope:

| Code | Description |
|---|---|
| 402 | Invalid argument |
| 501 | Action failed / GOST unreachable |
| 606 | Action not authorized |
| 713 | SpecifiedArrayIndexInvalid |
| 714 | NoSuchEntry |
| 715 | Port out of range (1-65535) |
| 716 | ConflictInMappingEntry |

## Lease Duration Logic

`AddPortMapping` clamps lease duration to max 604800 (7 days). If `NewLeaseDuration` is 0 or absent, falls back to `Config.LEASE_DURATION`.

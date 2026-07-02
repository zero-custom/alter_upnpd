# upnp_soap.py — UPnP SOAP Action Handler

Parses incoming SOAP requests, dispatches to the correct action handler, and builds SOAP XML responses for the WANIPConnection:1, WANCommonInterfaceConfig:1, and Layer3Forwarding:1 services.

## Service Architecture

Three action registries (plain dicts) map action names to handler methods:

| Registry | Service | Default URN |
|---|---|---|
| `_SOAP_HANDLERS` | WANIPConnection:1 | `urn:schemas-upnp-org:service:WANIPConnection:1` |
| `_CIC_HANDLERS` | WANCommonInterfaceConfig:1 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` |
| `_L3F_HANDLERS` | Layer3Forwarding:1 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` |

Actions are registered as plain dict entries — method names mapped to handler strings at class body level.

## `UPnPSOAPHandler`

### Dispatchers

| Method | Registry | Routes bound in `app.py` |
|---|---|---|
| `handle_wanipconnection()` | `_SOAP_HANDLERS` | `/ctl/IPConn`, `/ctl/WANIPCn`, `/ctl/WANPPPCn` |
| `handle_wancommonifconfig()` | `_CIC_HANDLERS` | `/ctl/CmnIfCfg` |
| `handle_l3forwarding()` | `_L3F_HANDLERS` | `/ctl/L3F` |

All dispatchers share `_handle_service_request()` which:
1. Checks ACL (if `EnvConfig.acl_enabled`) — blocks IPs not in `EnvConfig.acl_allowed_subnets`.
2. Reads the raw SOAP XML body from the Flask request.
3. Parses via `parse_soap_body()` to extract action name and parameters.
4. Sniffs the `SOAPAction` header to determine the action name (falls back to parsed body action).
5. Looks up the handler in the registry and calls it with parsed parameters.
6. Returns the handler's XML response as a Flask `Response`.

### SOAP Action Handlers (WANIPConnection:1)

| Action | Description |
|---|---|
| `AddPortMapping` | Creates or renews a GOST port mapping. Captures `NewRemoteHost` and `NewEnabled` in addition to standard UPnP fields. Checks `get_port_mapping_by_port()` for existing mappings — same-client renews via `update_port_mapping()` (PUT, refreshes `created_at`), different-client returns `718 ConflictInMappingEntry`. Calls `gost.add_port_mapping()` for new mappings. |
| `DeletePortMapping` | Deletes a GOST port mapping by constructing service name `upnp_{external_port}_{protocol}`. Calls `gost.delete_port_mapping()`. |
| `GetGenericPortMappingEntry` | Returns the Nth mapping (index-based pagination via `get_port_mapping_by_index`). Includes `lease_duration_remaining`. |
| `GetSpecificPortMappingEntry` | Returns mapping matching external port + protocol + remote host from `get_port_mappings()`. |
| `GetPortMappingNumberOfEntries` | Returns the total count of UPnP mappings. |
| `GetExternalIPAddress` | Returns STUN-discovered IP when `EnvConfig.stun` is enabled, otherwise `192.0.2.1`. |
| `GetConnectionTypeInfo` | Returns `IP_Routed` (static). |
| `GetLinkLayerMaxBitRates` | Returns 0 (static). |
| `GetStatusInfo` | Returns `Connected`, `ERROR_NONE`, and uptime. |
| `GetNATRSIPStatus` | Returns RSIP unavailable, NAT enabled. |
| `SetConnectionType` | Returns fault 501 (Action failed). |
| `RequestConnection` | Returns fault 501 (Action failed). |
| `ForceTermination` | Returns fault 501 (Action failed). |

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

| 713 | SpecifiedArrayIndexInvalid |
| 714 | NoSuchEntry |
| 715 | Port out of range (1-65535) |
| 718 | ConflictInMappingEntry (replaces 716 in v1.0.2) |

## Lease Duration Logic

`AddPortMapping` clamps lease duration to max 604800 (7 days). If `NewLeaseDuration` is 0 or absent, falls back to `EnvConfig.lease_duration`.

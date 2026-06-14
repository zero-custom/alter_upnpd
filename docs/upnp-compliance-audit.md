# UPnP IGD Compliance Audit Report

**Date:** 2026-06-14
**Target:** `alter_upnpd` v1.0.2
**Spec Baseline:** UPnP IGD 1.0 (WANIPConnection:1, WANPPPConnection:1, WANCommonInterfaceConfig:1, Layer3Forwarding:1)

---

## Overall Conclusion

**No critical compliance gaps found.** The core port mapping flow (add/delete/query) is fully compliant with UPnP IGD 1.0. The SSDP discovery protocol works correctly. Minor gaps are concentrated in statistics query and connection management Actions, which have **no impact** on mainstream UPnP clients (miniupnpc, Transmission, qBittorrent).

---

## Per-Service Audit

### 1. WANIPConnection:1

Device descriptor: `xml/WANIPCn.xml`
Handler: `upnp_soap.py → UPnPSOAPHandler.handle_ipconnection()`

| UPnP Action | Status | Notes |
|---|---|---|
| `AddPortMapping` | ✅ **Complete** | Calls `gost_client.add_port_mapping()` for new mappings, `update_port_mapping()` for same-client renew (PUT in-place, refreshes lease). Conflict returns 718. Security Mode blocks cross-IP mapping (718). |
| `DeletePortMapping` | ✅ **Complete** | Calls `gost_client.delete_port_mapping()`, 404 silently handled. Security Mode checks mapping ownership — returns 714 if owned by different client. |
| `GetGenericPortMappingEntry` | ✅ **Complete** | Iterates by index, returns standard UPnP field format |
| `GetSpecificPortMappingEntry` | ✅ **Complete** | Finds exact match by protocol + external port |
| `GetExternalIPAddress` | ✅ **Complete** | Gets public IP via STUN, falls back to `1.2.3.4` |
| `GetStatusInfo` | ⚠️ **Placeholder** | Returns hardcoded `"UPnP Ready"`, `"Connected"`, `1000` (spec allows multiple interpretations) |
| `GetNATRSIPStatus` | ✅ **Correct** | `NATEnabled=true, RSIPAvailable=false` |
| `SetConnectionType` | ⚠️ **Placeholder** | Returns 501 Action failed (v1.0.2: changed from 606 to 501) |
| `GetConnectionTypeInfo` | ✅ **Complete** | Returns `"IP_Routed"` |
| `ForceTermination` | ⚠️ **Placeholder** | Returns 501 Action failed |
| `RequestConnection` | ⚠️ **Placeholder** | Returns 501 Action failed |
| `DeletePortMappingRange` | ❌ **Not implemented** | Optional in IGD:1, required in IGD:2 |
| `GetListOfPortMappings` | ❌ **Not implemented** | Optional in IGD:1 |
| `AddAnyPortMapping` | ❌ **Not implemented** | IGD:2 addition |
| `GetInboundPinhole` | ❌ **Not implemented** | IGD:2 addition |
| `SetIdleTime` | ❌ **Not implemented** | Optional in IGD:2 |
| `StartAutoRedeemTime` | ❌ **Not implemented** | Optional in IGD:2 |

### 2. WANPPPConnection:1

Device descriptor: Same as `WANIPCn.xml`
Route: `app.py` route `/ctl/WANPPPCn` → `soap_handler.handle_wanipconnection()` — **shares the same handler as WANIPConnection**

| UPnP Action | Status | Notes |
|---|---|---|
| All Actions | ⚠️ **Partial** | Shared WANIPConnection handler covers most port mapping operations; `GetLinkLayerMaxBitRates` / `SetConnectionType` (PPPoE-specific) work via unified parsing |

### 3. WANCommonInterfaceConfig:1

Device descriptor: `xml/WANCfg.xml`
Handler: `upnp_soap.py → handle_wancommonifconfig()`

| UPnP Action | Status | Notes |
|---|---|---|
| `GetCommonLinkProperties` | ⚠️ **Placeholder** | Returns hardcoded `LinkStatus="Up"`, `UpSpeed=100000000`, `DownSpeed=100000000` |
| `GetTotalBytesSent` | ⚠️ **Placeholder** | Returns 0 |
| `GetTotalBytesReceived` | ⚠️ **Placeholder** | Returns 0 |
| `GetTotalPacketsSent` | ⚠️ **Placeholder** | Returns 0 |
| `GetTotalPacketsReceived` | ⚠️ **Placeholder** | Returns 0 |

### 4. Layer3Forwarding:1

Device descriptor: `xml/L3F.xml`
Handler: `upnp_soap.py → handle_l3forwarding()`

| UPnP Action | Status | Notes |
|---|---|---|
| `GetDefaultConnectionService` | ⚠️ **Placeholder** | Returns default UDN |
| `SetDefaultConnectionService` | ⚠️ **Placeholder** | Accepts request but ignores params |

---

## SSDP Protocol Audit

| Feature | Status | Notes |
|---|---|---|
| NOTIFY periodic alive | ✅ **Working** | Sends 8 service/device notifications every `Config.SSDP_NOTIFY_INTERVAL` (default 180s) |
| NOTIFY byebye | ✅ **Working** | Sends 8 byebye notifications on shutdown |
| M-SEARCH response | ✅ **Correct** | Matches `ST` request via `_ST_USN_MAP`; `ssdp:all` returns 8 responses (one per device/service type) |
| BOOTID.UPNP.ORG | ✅ **Implemented** | Set to `int(time.time())` on boot, included in NOTIFY and M-SEARCH responses |
| CONFIGID.UPNP.ORG | ✅ **Implemented** | Static value `1`, included in NOTIFY and M-SEARCH responses |
| DATE | ✅ **Implemented** | RFC 1123 format in M-SEARCH responses |
| SEARCHPORT.UPNP.ORG | ⚠️ **Missing** | Non-essential |

**SSDP M-SEARCH response ST field handling:** The current code echoes the request's `ST` value back in the response header — **this is correct UPnP behavior** (UDA 1.1 §1.2.3 requires the M-SEARCH response ST to equal the request ST, or return the specific device type when `ssdp:all` is requested).

---

## XML Device Descriptor Audit

| File | Status | Notes |
|---|---|---|
| `rootDesc.xml` | ✅ **Correct** | Contains 3-layer IGD hierarchy (IGD → WANDevice → WANConnectionDevice), URL injected dynamically via Jinja2 |
| `WANIPCn.xml` | ✅ **Correct** | Contains WANIPConnection:1 SCPD, declares all standard Actions and state variables |
| `WANCfg.xml` | ✅ **Correct** | Contains WANCommonInterfaceConfig:1 SCPD |
| `L3F.xml` | ✅ **Correct** | Contains Layer3Forwarding:1 SCPD |

---

## Security Audit

| Item | Status | Notes |
|---|---|---|
| ACL IP filtering | ✅ **Implemented** | `ACL_ENABLED` + `ACL_ALLOWED_SUBNETS` restrict source IPs |
| Security Mode (AddPortMapping) | ✅ **Implemented** | `SECURE_MODE` (default enabled) blocks mapping to a different IP than the requester. Returns 718. |
| Security Mode (DeletePortMapping) | ✅ **Implemented** | Blocks deletion of mappings owned by a different client. Returns 714. |
| Error info hiding | ✅ **Implemented** | Conflict/ownership errors use the same error code (718/714) regardless of actual conflict — no information leakage. |
| `RemoteHost` validation | ⚠️ **Could improve** | No restriction on `RemoteHost` origin (spec says it can be ignored) |
| Lease expiry cleanup | ✅ **Implemented** | Background thread checks and cleans expired mappings every 60s (configurable) |

---

## Summary Action Items

| Priority | Item | Impact |
|---|---|---|
| 🟡 Medium | Return actual status from `GetStatusInfo` | Some clients may check connection state |
| 🟢 Low | Return real values for stats APIs (TotalBytes/Packets) | Management and monitoring scenarios |
| 🟢 Low | Make `RequestConnection` actually trigger STUN refresh | Only useful when client explicitly calls it |
| 🟢 Low | Hostname resolution for InternalClient | If client sends hostname instead of IP, mapping fails |
| 🟢 Low | WAN IP reported consistently as source from STUN | Some clients rely on consistent IP format |
| ⚪ None | GENA event notifications | Mainstream clients don't rely on this |

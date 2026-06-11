# upnp_soap.py — UPnP SOAP 动作处理器

解析入站 SOAP 请求，分发到对应的动作处理器，构造 SOAP XML 响应。支持 WANIPConnection:1、WANCommonInterfaceConfig:1 和 Layer3Forwarding:1 服务。

## 服务架构

三个动作注册表（普通字典）将动作名映射到处理方法：

| 注册表 | 服务 | 默认 URN |
|---|---|---|
| `SOAP_ACTIONS` | WANIPConnection:1 | `urn:schemas-upnp-org:service:WANIPConnection:1` |
| `CIC_ACTIONS` | WANCommonInterfaceConfig:1 | `urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1` |
| `L3F_ACTIONS` | Layer3Forwarding:1 | `urn:schemas-upnp-org:service:Layer3Forwarding:1` |

动作通过 `@soap_action`、`@cic_action` 或 `@l3f_action` 装饰器注册。

## `UPnPSOAPHandler`

### 分发器

| 方法 | 注册表 | `app.py` 中绑定的路由 |
|---|---|---|
| `handle_wanipconnection()` | `SOAP_ACTIONS` | `/ctl/IPConn`、`/ctl/WANIPCn`、`/ctl/WANPPPCn` |
| `handle_wancommonifconfig()` | `CIC_ACTIONS` | `/ctl/CmnIfCfg` |
| `handle_l3forwarding()` | `L3F_ACTIONS` | `/ctl/L3F` |

所有分发器共享 `_handle_service_request()`：
1. 检查 ACL（若 `Config.ACL_ENABLED`）——阻止不在 `Config.ACL_ALLOWED_SUBNETS` 中的 IP。
2. 从 Flask 请求中读取原始 SOAP XML 体。
3. 通过 `parse_soap_body()` 解析出动作名和参数。
4. 从 `SOAPAction` 头中嗅探动作名（解析失败时退回到从请求体中提取）。
5. 在注册表中查找处理器并调用，传入解析后的参数。
6. 以 Flask `Response` 形式返回处理器的 XML 响应。

### SOAP 动作处理程序（WANIPConnection:1）

| 动作 | 说明 |
|---|---|
| `AddPortMapping` | 创建 GOST 端口映射。除了标准 UPnP 字段外，捕获 `NewRemoteHost` 和 `NewEnabled`。调用 `has_port_mapping()` 检测冲突（错误 716）。调用 `gost.add_port_mapping()` 传入所有参数。 |
| `DeletePortMapping` | 通过构造 service 名称 `upnp_{external_port}_{protocol}` 删除 GOST 端口映射。调用 `gost.delete_port_mapping()`。 |
| `GetGenericPortMappingEntry` | 返回第 N 个映射（基于索引的翻页，使用 `get_port_mapping_by_index`）。包含 `lease_duration_remaining`。 |
| `GetSpecificPortMappingEntry` | 从 `get_port_mappings()` 返回匹配外网端口+协议+远程主机的映射。 |
| `GetPortMappingNumberOfEntries` | 返回 UPnP 映射的总数。 |
| `GetExternalIPAddress` | 当 `Config.STUN` 启用时返回 STUN 发现的外网 IP，否则返回 `1.2.3.4`。 |
| `GetConnectionTypeInfo` | 返回 `IP_Routed`（静态）。 |
| `GetLinkLayerMaxBitRates` | 返回 0（静态）。 |
| `GetStatusInfo` | 返回 `Connected`、`ERROR_NONE` 和运行时间。 |
| `GetNATRSIPStatus` | 返回 RSIP 不可用、NAT 启用。 |
| `SetConnectionType` | 返回错误 606（Action not authorized）。 |
| `RequestConnection` | 返回错误 606（Action not authorized）。 |
| `ForceTermination` | 返回错误 606（Action not authorized）。 |

### WANCommonInterfaceConfig 处理器

| 动作 | 说明 |
|---|---|
| `GetCommonLinkProperties` | 静态：Ethernet、0 速率、Up。 |
| `GetTotalBytesSent` | 返回 0。 |
| `GetTotalBytesReceived` | 返回 0。 |
| `GetTotalPacketsSent` | 返回 0。 |
| `GetTotalPacketsReceived` | 返回 0。 |

### Layer3Forwarding 处理器

| 动作 | 说明 |
|---|---|
| `GetDefaultConnectionService` | 返回 `urn:upnp-org:serviceId:WANIPConn1`。 |
| `SetDefaultConnectionService` | 空成功响应。 |

## 命名空间处理

`build_soap_response()` 接受可选的 `service_urn` 参数，默认为最后设置的 `_current_service_urn`。WANIPConnection 和 WANPPPConnection 请求都走 `handle_wanipconnection()`。

## 错误处理

SOAP 错误使用 UPnP 错误码包装在 `<s:Fault>` 结构中：

| 错误码 | 说明 |
|---|---|
| 402 | 无效参数 |
| 501 | 操作失败 / GOST 不可达 |
| 606 | 操作未授权 |
| 713 | SpecifiedArrayIndexInvalid |
| 714 | NoSuchEntry |
| 715 | 端口超出范围（1-65535） |
| 716 | ConflictInMappingEntry |

## 租期逻辑

`AddPortMapping` 将租期限制在最多 604800 秒（7 天）。如果 `NewLeaseDuration` 为 0 或缺失，则退回到 `Config.LEASE_DURATION`。

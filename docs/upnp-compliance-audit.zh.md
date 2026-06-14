# UPnP IGD 规范合规审计报告

**日期：** 2026-06-14
**审计对象：** `alter_upnpd` v1.0.2
**基准规范：** UPnP IGD 1.0 (WANIPConnection:1, WANPPPConnection:1, WANCommonInterfaceConfig:1, Layer3Forwarding:1)

---

## 总体结论

**没有致命合规缺口。** 核心端口映射流程（添加/删除/查询）完全符合 UPnP IGD 1.0 规范。SSDP 发现协议正常运行。次要差距集中在统计查询类和连接管理类 Action 上，这些对于主流 UPnP 客户端（miniupnpc、Transmission、qBittorrent）**无影响**。

---

## 按服务审计

### 1. WANIPConnection:1

设备描述文件：`xml/WANIPCn.xml`
处理器：`upnp_soap.py → UPnPSOAPHandler.handle_ipconnection()`

| UPnP Action | 状态 | 说明 |
|---|---|---|
| `AddPortMapping` | ✅ **完整** | 新映射调用 `gost_client.add_port_mapping()`；同客户端续约用 `update_port_mapping()`（PUT 原地更新，刷新租期）。冲突返回 718。Security Mode 阻止跨 IP 映射（718）。 |
| `DeletePortMapping` | ✅ **完整** | 调用 `gost_client.delete_port_mapping()`，404 正常吞掉。Security Mode 检查映射归属——非本人映射返回 714。 |
| `GetGenericPortMappingEntry` | ✅ **完整** | 按索引遍历，返回标准 UPnP 字段格式 |
| `GetSpecificPortMappingEntry` | ✅ **完整** | 按协议+外网端口精确查找 |
| `GetExternalIPAddress` | ✅ **完整** | 通过 STUN 获取公网 IP，回退到 `1.2.3.4` |
| `GetStatusInfo` | ⚠️ **占位** | 返回硬编码 `"UPnP Ready"`、`"Connected"`、`1000`（规范允许多种实现） |
| `GetNATRSIPStatus` | ✅ **正确** | `NATEnabled=true, RSIPAvailable=false` |
| `SetConnectionType` | ⚠️ **占位** | 返回 501 Action failed（v1.0.2：原 606 改为 501） |
| `GetConnectionTypeInfo` | ✅ **完整** | 返回 `"IP_Routed"` |
| `ForceTermination` | ⚠️ **占位** | 返回 501 Action failed |
| `RequestConnection` | ⚠️ **占位** | 返回 501 Action failed |
| `DeletePortMappingRange` | ❌ **未实现** | IGD:1 可选，IGD:2 才必需 |
| `GetListOfPortMappings` | ❌ **未实现** | IGD:1 可选 |
| `AddAnyPortMapping` | ❌ **未实现** | IGD:2 新增 |
| `GetInboundPinhole` | ❌ **未实现** | IGD:2 新增 |
| `SetIdleTime` | ❌ **未实现** | IGD:2 可选 |
| `StartAutoRedeemTime` | ❌ **未实现** | IGD:2 可选 |

### 2. WANPPPConnection:1

设备描述文件：同 `WANIPCn.xml`
路由器：`app.py` 中路由 `/ctl/WANPPPCn` → `soap_handler.handle_wanipconnection()` — **与 WANIPConnection 共用同一处理器**

| UPnP Action | 状态 | 说明 |
|---|---|---|
| 全部 Action | ⚠️ **部分** | 共享 WANIPConnection 处理器可覆盖大部分端口映射操作；`GetLinkLayerMaxBitRates` / `SetConnectionType`（PPPoE 特有）通过统一解析可工作 |

### 3. WANCommonInterfaceConfig:1

设备描述文件：`xml/WANCfg.xml`
处理器：`upnp_soap.py → handle_wancommonifconfig()`

| UPnP Action | 状态 | 说明 |
|---|---|---|
| `GetCommonLinkProperties` | ⚠️ **占位** | 返回硬编码 `LinkStatus="Up"`、`UpSpeed=100000000`、`DownSpeed=100000000` |
| `GetTotalBytesSent` | ⚠️ **占位** | 返回 0 |
| `GetTotalBytesReceived` | ⚠️ **占位** | 返回 0 |
| `GetTotalPacketsSent` | ⚠️ **占位** | 返回 0 |
| `GetTotalPacketsReceived` | ⚠️ **占位** | 返回 0 |

### 4. Layer3Forwarding:1

设备描述文件：`xml/L3F.xml`
处理器：`upnp_soap.py → handle_l3forwarding()`

| UPnP Action | 状态 | 说明 |
|---|---|---|
| `GetDefaultConnectionService` | ⚠️ **占位** | 返回默认 UDN |
| `SetDefaultConnectionService` | ⚠️ **占位** | 接受请求但忽略参数 |

---

## SSDP 协议审计

| 特性 | 状态 | 说明 |
|---|---|---|
| NOTIFY 定期 alive | ✅ **正常** | 每 `Config.SSDP_NOTIFY_INTERVAL`（默认 180s）发送 8 条服务/设备通知 |
| NOTIFY byebye | ✅ **正常** | 进程退出时发送 8 条 byebye |
| M-SEARCH 响应 | ✅ **正确** | 通过 `_ST_USN_MAP` 匹配 `ST`；`ssdp:all` 返回 8 条响应（每种设备/服务类型各一条） |
| BOOTID.UPNP.ORG | ✅ **已实现** | 启动时设为 `int(time.time())`，包含在 NOTIFY 和 M-SEARCH 响应中 |
| CONFIGID.UPNP.ORG | ✅ **已实现** | 静态值 `1`，包含在 NOTIFY 和 M-SEARCH 响应中 |
| DATE | ✅ **已实现** | M-SEARCH 响应中使用 RFC 1123 格式 |
| SEARCHPORT.UPNP.ORG | ⚠️ **缺失** | 非必需 |

**SSDP M-SEARCH 响应 ST 字段处理：** 当前代码将请求中的 `ST` 值原样写入响应头 — **这是正确的 UPnP 行为**（UDA 1.1 第 1.2.3 节要求 M-SEARCH 响应 ST 等于请求的 ST，或 `ssdp:all` 时返回特定设备类型）。

---

## XML 设备描述审计

| 文件 | 状态 | 说明 |
|---|---|---|
| `rootDesc.xml` | ✅ **正确** | 包含 IGD 设备的 3 层层次（IGD → WANDevice → WANConnectionDevice），URL 通过 Jinja2 动态注入 |
| `WANIPCn.xml` | ✅ **正确** | 包含 WANIPConnection:1 的 SCPD，声明了所有标准 Action 和状态变量 |
| `WANCfg.xml` | ✅ **正确** | 包含 WANCommonInterfaceConfig:1 SCPD |
| `L3F.xml` | ✅ **正确** | 包含 Layer3Forwarding:1 SCPD |

---

## 安全审计

| 项目 | 状态 | 说明 |
|---|---|---|
| ACL IP 过滤 | ✅ **已实现** | `ACL_ENABLED` + `ACL_ALLOWED_SUBNETS` 限制来源 IP |
| Security Mode（AddPortMapping） | ✅ **已实现** | `SECURE_MODE`（默认启用）阻止映射到非请求者 IP。返回 718。 |
| Security Mode（DeletePortMapping） | ✅ **已实现** | 阻止删除他人映射。返回 714。 |
| 错误信息隐藏 | ✅ **已实现** | 冲突/归属错误使用相同错误码（718/714），不暴露具体冲突原因。 |
| `RemoteHost` 验证 | ⚠️ **可改进** | 当前不限制 `RemoteHost` 来源（规范建议可忽略） |
| 租赁超时清理 | ✅ **已实现** | 后台线程每 60s（可配）检查并清理过期映射 |

---

## 总结行动项

| 优先级 | 项目 | 影响范围 |
|---|---|---|
| 🟡 中 | `GetStatusInfo` 返回实际状态 | 部分客户端可能检查连接状态 |
| 🟢 低 | 统计类 API（TotalBytes/Packets）返回真实值 | 管理和监控场景 |
| 🟢 低 | `RequestConnection` 实际调用 STUN 刷新 | 仅在客户端显式调用时有用 |
| 🟢 低 | InternalClient 主机名解析 | 若客户端发送主机名而非 IP，映射会失败 |
| 🟢 低 | WAN IP 来源一致性问题 | 部分客户端依赖一致的 IP 格式 |
| ⚪ 无需处理 | GENA 事件通知 | 主流客户端不依赖 |

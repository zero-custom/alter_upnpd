# Changelog

## 1.2.0 (2026-06-26)

### Added
- **GOST WebUI 监控仪表板**（`webui.py`）：PyWebIO + ECharts 实时仪表板，路由 `/`，替代旧纯文本状态页面。
  - **概览卡片**：映射数 / 活动连接 / 总流量 / 错误数四张信息卡
  - **流量趋势图**：入站/出站带宽 + 连接数折线图（pyecharts + ECharts），默认最近 1 小时，支持拖拽缩放
  - **端口映射表格**：可展开详情行显示各端口独立流量图表，批量删除复选框
  - **添加映射表单**：折叠式添加表单（External Port / Protocol / Internal Client / Internal Port / Description / Lease）
  - **实时刷新**：后台线程每 10 秒增量更新，映射变化时保留选中状态安全重绘
  - **ECharts 本地化**：ECharts 6.x 从 `/static/echarts.min` 加载（CDN 仅启动时检查）
- `GOST_WEBUI_REFRESH_INTERVAL` 环境变量（默认 `10` 秒）
- `GOST_WEBUI_HISTORY_POINTS` 环境变量（默认 `8640`，10 秒间隔 = 24 小时）
- `GOST_METRICS_URL` 环境变量，配置 Prometheus metrics URL（空 = 自动发现）

### Changed
- `.env.example` 新增 WebUI 相关环境变量

---

## 1.1.1 (2026-06-20)

### Added
- `UPSTREAM_INTERNAL_HOST` 环境变量：同步端口映射到上游 IGD 时，可覆写 `NewInternalClient` 字段。为空时保持原有行为（上游 IGD 自动填入 SOAP 请求来源 IP）。

### Fixed
- **GOST 重启后自动恢复失效**：`GostClient._services_cache` 无 TTL 过期机制，GOST 重启后 alter_upnpd 持续返回过期缓存。修复：缓存改为 30 秒 TTL 自动过期（add/update/delete 操作仍即时清空缓存），确保 GOST 重启后能被及时发现并触发自动重新添加。

---

## 1.1.0 (2026-06-14)

### Added
- **上游 IGD 端口映射同步**：新增 `upstream_client.py` 模块，通过 `UPSTREAM_IGD_URL` 配置上游 UPnP IGD 的 rootDesc.xml URL，自动发现 WANIPConnection 控制端点。
- **Add/Delete 同步**：AddPortMapping / DeletePortMapping 操作成功时自动同步至上游 IGD。
- **映射拓扑**：上游映射使用与下游相同的 `NewExternalPort`，`NewInternalClient` 自动设为 alter_upnpd 宿主机 IP，`NewInternalPort` 等于下游 `NewExternalPort`。
- **静默降级**：上游 IGD 不可达或返回错误时仅记录警告，不影响下游 GOST 映射的正常使用。
- `UPSTREAM_IGD_URL` 环境变量（`config.py`）。

---

## 1.0.2 (2026-06-13)

### Fixed
- **修复 AddPortMapping 冲突检测**: 同客户端覆盖续约（PUT 更新 metadata 刷新租期），冲突错误码 `716` → `718`。
- **NewInternalClient 空值回填**: 客户端不传 `NewInternalClient` 时自动回填 `request.remote_addr`。
- **RSIPAvailable 虚假声明**: `1` → `0`（IGDv1 不支持 RSIP）。
- **未知 Action 错误码**: `606 Action not authorized` → `501 Action failed`。

### Security
- **AddPortMapping Security Mode**: 新增 `SECURE_MODE` 配置（默认启用），阻止客户端将端口映射到非自身 IP，返回 `718 ConflictInMappingEntry`。
- **DeletePortMapping Security Mode**: 阻止客户端删除他人映射，返回 `714 NoSuchEntryInArray`。
- 错误信息遵从安全最佳实践——不暴露映射归属信息。

### Changed
- **SSDP NOTIFY 消息**: 新增 `BOOTID.UPNP.ORG`、`CONFIGID.UPNP.ORG` 头。
- **SSDP M-SEARCH 响应**: `DATE` 头从空字符串改为 RFC 1123 格式当前时间；新增 `BOOTID.UPNP.ORG`、`CONFIGID.UPNP.ORG`。
- **ssdp:all 搜索**: 回复从 1 条扩展为 8 条（rootdevice + 各设备/服务）。

### Added
- `SECURE_MODE` 环境变量（`config.py`）。
- `GostClient.get_port_mapping_by_port()` 方法，按端口/协议查映射详情。
- `GostClient.update_port_mapping()` 方法，PUT 更新已有服务 metadata。

---

## 1.0.1 (2026-06-08)

### Fixed
- 修复 Docker 容器内 SSDP 多播绑定失败时的优雅降级（PermissionError 捕获）。
- 修复 `NewLeaseDuration` 空值/非数字时的异常处理。

### Changed
- SOAP 处理器合并，`WANPPPConnection` 与 `WANIPConnection` 共享统一路由 `/ctl/IPConn`。
- `GetStatusInfo` 返回实际运行时长（`time.time() - _start_time`）。
- `ACL_ENABLED` 默认改为 `true`，默认拒绝外部 IP 访问控制端点。
- 租赁过期清理线程默认间隔从 300s 改为 60s。
- `SERVER_ID` 统一定义为 `Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0`。

### Added
- 新增 `ACL_ENABLED` / `ACL_ALLOWED_SUBNETS` 环境变量。
- 新增 `GOST_API_USERNAME` / `GOST_API_PASSWORD` 配置，支持 GOST API 认证。
- 新增 `/health` 健康检查端点，返回 GOST 连接状态和映射数量。
- SGID 租赁过期自动清理机制（`run_lease_cleanup`）。

---

## 1.0.0 (2026-06-07)

### Initial
- 项目创建，基于 Flask + `ssdp` 库 + `py3stun` 实现 UPnP IGD 网关。
- 支持 WANIPConnection:1 核心操作：`AddPortMapping` / `DeletePortMapping` / `GetGenericPortMappingEntry` / `GetSpecificPortMappingEntry` / `GetExternalIPAddress`。
- 支持 WANCommonInterfaceConfig:1 / Layer3Forwarding:1 基础操作。
- SSDP 设备发现：NOTIFY alive/byebye + M-SEARCH 响应。
- STUN 外网 IP 探测（`stun.l.google.com:19302`）。
- GOST API CRUD 客户端，带重试、缓存、租赁过期查询。
- Docker 部署：`docker-compose.yml` + `Dockerfile`。

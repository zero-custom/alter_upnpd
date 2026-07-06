# Changelog

## 1.3.2 (2026-07-05)

### Fixed

- **图表时间轴失真**：ECharts x 轴从 `type: 'category'` + `HH:MM:SS` 字符串切换为 `type: 'time'` + 毫秒时间戳 (`int(p.timestamp * 1000)`)。消除跨零点（24h+ 运行）标签重复导致的折线跳跃。主聚合图与各端口详情图同步修复。
- **降采样死代码**：`display_max` 与 `max_history` 解耦，从 `8640=8640` 改为 `min(history_points, 1000)` vs `8640`。`_downsample()` 正式生效，8640 点降至 ≤1000 点渲染，减少浏览器内存压力。

### Cleanup

- **死代码删除**：移除 `upnp_soap.py` 中无调用者的 `parse_soap_body()` / `build_soap_response()` / `build_fault_response()`；移除 `webui_probe.py` 中无调用者的 `Probe.on()` / `off()` / `active` 及 `Callable` import；移除 `upstream_client.py` 中未使用的 `Optional` import；移除 `debug_launcher.py` 中未使用的 `sys` import；移除 `webui.py` 中不再引用的 `get_all_services_stats` import。
- **`_fmt_time` 去重**：删除 `debug_launcher.py`/`webui_probe.py` 中的本地副本，统一从 `webui_format` 导入。
- **零 docstring 政策**：移除全部 7 处文档字符串（`debug_launcher.py` 模块、`stun_client.py:wait_ready`、`upstream_client.py:reconcile`、`webui_probe.py` 模块 + `Probe` 类、`webui_render.py:_init_chart` + `_render_charts`）。知识全部迁移至 `docs/` 目录。

---

## 1.3.1 (2026-07-02)

### Fixed

- **STUN 启动时序竞争**：`StunClient` 新增 `_ready` Event + `wait_ready()`，`AppLifecycle.start()` 在 STUN 启动后等待最多 10s 直到首次解析完成（或超时），然后才启动 SSDP 线程。避免客户端在 STUN 完成前查询 `GetExternalIPAddress` 得到 fallback IP `192.0.2.1`。

### Changed

- **`StunClient.wait_ready()`**: 新增公开方法，阻塞直到首次 STUN 刷新完成（或超时），返回 `bool`。

---

## 1.3.0 (2026-06-27)

### 架构重构：依赖注入 + 模块化

v1.3.0 的核心工作是架构层面的系统性重构——将原本耦合在 `app.py` 和各模块中的全局状态、内联逻辑提取为职责单一的类，通过构造函数注入建立显式依赖关系。目标是让每个模块可独立测试、可替换、可推理。

**`app.py` 瘦身**：移除全部模块级全局变量（`_shutdown_event`、`_ssdp_thread`、`_lease_thread`、`TEMPLATE_CACHE`、`_TEMPLATE_VARS`）和内联后台函数（`run_ssdp`、`run_lease_cleanup`、`init_background_services`、`shutdown_background_services`）。提取为三个新模块：
- `lifecycle.py`：`AppLifecycle` 类，管理 SSDP 公告 + 租赁清理线程生命周期
- `template.py`：`TemplateRenderer` 类，带缓存失效的 XML 模板渲染引擎
- `app_health.py`：`HealthService` 类，健康检查逻辑

**`gost_client.py` 分层**：从单一日志客户端拆分为四层职责链：
- `GostTransport`：HTTP 传输层（认证、重试、超时）
- `PortMappingRepository`：端口映射 CRUD + 带 TTL 的缓存层
- `GostMetricsClient`：Prometheus 指标采集
- `GostClient`：门面，保持向后兼容

**`upnp_soap.py` 精简**：SOAP XML 解析移至 `soap_xml.py`，ACL 验证逻辑移至 `acl.py`，处理器专注于动作分发。

**`ssdp_responder.py` 优化**：`UPNP_NT_LIST` 常量提取，alive 循环合并，消除重复的发送逻辑。`SSDPResponder` 生命周期管理上移至 `AppLifecycle`。

**`stun_client.py` / `upstream_client.py` 类改造**：从模块级函数 + 全局变量重构为类，配置通过构造函数注入。

**`webui.py` 拆分**：渲染逻辑抽离为 `webui_format.py`（表格/图表数据格式化）+ `webui_render.py`（ECharts JS/CSS 内联渲染）。

**`config.py` 配置模型重构**：引入 `EnvConfig` + `load_env_config()`，支持 strict 模式验证和 yaml 配置源。`GostClientConfig` 等子配置类分离。

### 测试
- 新增 `test/test_ssdp.py`（17 个 SSDP 专项测试），测试总数 187
- 移除 `test/test_integration.py`（功能已被 SSDP 测试覆盖）

---



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

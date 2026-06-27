# alter_upnpd — Handoff（中文）

## 已完成的工作

### 1. AGENTS.md 创建与完善
- 编写初始 `AGENTS.md`，包含架构、目录结构、SOAP 注册表、命令、测试、环境变量、反模式、SSDP 常量。
- 根据反馈迭代完善：添加关键事实、修正 XML 文件描述、澄清 SOAP 注册表结构、添加已知限制章节。
- 为 v1.2.0 更新：添加 `webui.py` 到结构、查找表、API 路由和配置。

### 2. 中文文档（`.zh.md`）
- 为全部 7 个源文档文件创建中文版本（`*.zh.md`），与英文版（`.md`）并列存放：
  - `app`、`config`、`gost_client`、`gunicorn_config`、`ssdp_responder`、`stun_client`、`upnp_soap`
- 决定：同时保留 `.md`（英文）和 `.zh.md`（中文）作为兄弟文件，不互相覆盖。

### 3. Handoff 文档
- 在 `docs/` 中创建 `handoff.md`（英文）和 `handoff.zh.md`（中文），用于会话连续性。

### 4. v1.2.0 — GOST WebUI 仪表板
- **`webui.py`**：PyWebIO + ECharts 实时监控仪表板（路由 `/`）。
- 功能：概览卡片、流量趋势图、可展开映射表格（各端口独立图表）、添加映射表单、批量删除、10 秒自动刷新。
- CSS/JS 修复：斑马纹交替（`_applyZebra()`）、详情行宽度（`_countTableCols()` 返回 16）、`.markdown-body` 优先级前缀。
- 新增 `static_bp.py` + `static/` 目录，用于本地 ECharts 资源。
- 新增环境变量：`GOST_WEBUI_REFRESH_INTERVAL`、`GOST_WEBUI_HISTORY_POINTS`、`GOST_METRICS_URL`。

## 项目状态
- 三个 SOAP 注册表：`SOAP_ACTIONS`（WANIPConnection）、`CIC_ACTIONS`（WANCommonInterfaceConfig）、`L3F_ACTIONS`（Layer3Forwarding）。
- `webui.py` 通过 `pywebio.platform.flask.webio_view` 完整整合进 Flask 应用。
- `AGENTS.md`、`.env.example` 和所有程序文档已为 v1.2.0 更新。
- 保留之前会话的工作（metadata lease、lease cap、TTL 缓存、上游 IGD 同步）。

## 关键文件
- `alter_upnpd/AGENTS.md` — 纯项目 agent 指南
- `alter_upnpd/docs/` — 26 个程序文档文件（13 英文 + 13 中文）+ 2 个 handoff 文件
- `alter_upnpd/app/` — 10 个 Python 源文件 + `static/` + `xml/`

# alter_upnpd — Handoff（中文）

**版本**: v1.3.2 | **日期**: 2026-07-05

## 已完成的工作

### 1. v1.3.2 — 缺陷修复与代码清理
- **图表时间轴修复**：从 `type: "category"` + `HH:MM:SS` 切换为 ECharts `type: "time"` + 毫秒时间戳。消除跨零点的标签重复问题。主聚合图和端口详情图均适用。
- **死代码清理**：删除 `upnp_soap.py` 中 3 个未使用的方法（`parse_soap_body()` / `build_soap_response()` / `build_fault_response()`）、`webui_probe.py` 中无调用者的 `on()` / `off()` / `active`、以及多处陈旧 import。
- **降采样修复**：`display_max` 与 `max_history` 解耦——现在为 `min(history_points, 1000)` vs `8640`，`_downsample()` 从不生效变为生效。
- **`_fmt_time` 去重**：移除 `debug_launcher.py`/`webui_probe.py` 中 2 个本地副本；统一从 `webui_format` 导入。
- **文档清理**：删除全部 7 处文档字符串（零 docstring 政策）；更新 `upnp_soap.md` 中指向已删除方法的陈旧引用为 `SoapBodyParser.*`。
- **测试**：209 通过，2 个已有失败保持不变，零回归。

### 2. v1.2.0 — GOST WebUI 仪表板（上一会话）
- **`webui.py`**：PyWebIO + ECharts 实时监控仪表板（路由 `/`）。
- 功能：概览卡片、流量趋势图、可展开映射表格（各端口独立图表）、添加映射表单、批量删除、10 秒自动刷新。
- 新增 `static_bp.py` + `static/` 目录，用于本地 ECharts 资源。
- 新增环境变量：`GOST_WEBUI_REFRESH_INTERVAL`、`GOST_WEBUI_HISTORY_POINTS`、`GOST_METRICS_URL`。

### 3. 文档
- 为 `webui.py`、`webui_render.py`、`webui_format.py`、`upstream_client.py`、`debug_launcher.py`、`lifecycle.md` 创建中英双语文档。
- 在 `webui*.md` 中添加时间轴章节，记录 `type: "time"` + 毫秒时间戳方案。
- `CHART_DISTORTION_ANALYSIS.md` 位于项目根目录，包含根因分析和修复状态。

## 项目状态
- 三个 SOAP 注册表：`_SOAP_HANDLERS`（WANIPConnection）、`_CIC_HANDLERS`（WANCommonInterfaceConfig）、`_L3F_HANDLERS`（Layer3Forwarding）。
- `webui.py` 通过 `pywebio.platform.flask.webio_view` 完整整合进 Flask 应用。
- SOAP 解析现在通过 `SoapBodyParser` 类（`upnp_soap.py:SoapBodyParser`）。
- 降采样已生效，阈值为 1000 点。
- 零 docstring 政策已强制执行——所有知识存于 `docs/` 中。
- 保留之前会话的工作（metadata lease、lease cap、TTL 缓存、上游 IGD 同步）。

## 剩余待办
- 将 v1.3.2 部署到 ARM64 容器并验证 24 小时后图表显示正确。
- Y 轴 P95 裁剪（方案 2）——防止异常值端口压缩正常范围。
- 零值端口过滤（方案 4）——跳过 100% 为零的数据系列。

## 关键文件
- `alter_upnpd/AGENTS.md` — 纯项目 agent 指南
- `alter_upnpd/docs/` — 26 个程序文档文件（13 英文 + 13 中文）+ 2 个 handoff 文件
- `alter_upnpd/app/` — 10 个 Python 源文件 + `static/` + `xml/`
- `CHART_DISTORTION_ANALYSIS.md` — 图表失真分析及修复跟踪

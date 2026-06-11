# app.py — Flask 应用与入口点

主 Flask 应用程序。定义 HTTP 路由、模板渲染、后台服务生命周期和 `main()` 入口点。

## 路由

| 路径 | 方法 | 说明 |
|---|---|---|
| `/rootDesc.xml` | GET | 根设备描述 XML（Jinja2 渲染，填入 `LOCAL_IP`、`LOCAL_PORT`）。 |
| `/L3F.xml` | GET | Layer3Forwarding SCPD。 |
| `/WANCfg.xml` | GET | WANCommonInterfaceConfig SCPD。 |
| `/WANIPCn.xml` | GET | WANIPConnection SCPD。 |
| `/ctl/L3F` | POST | Layer3Forwarding SOAP 动作。 |
| `/ctl/CmnIfCfg` | POST | WANCommonInterfaceConfig SOAP 动作。 |
| `/ctl/IPConn` | POST | WANIPConnection SOAP 动作（主要路由）。 |
| `/ctl/WANIPCn` | POST | WANIPConnection SOAP 动作（别名路由）。 |
| `/ctl/WANPPPCn` | POST | WANPPPConnection SOAP 动作（与 IPConn 同一处理器）。 |
| `/` | GET | 状态页面，显示 IP:端口。 |
| `/health` | GET | JSON 健康检查（本地 IP、端口、GOST API URL、GOST 连通性、映射数量、版本）。 |

任何未在上述列表中列出的 `*.xml` 路径由通配路由 `/<path:filename>` 处理，渲染 `xml/` 目录中对应的模板。

## 模板渲染

XML 模板从 `app/xml/` 通过 Jinja2 加载，使用基于 mtime 的缓存失效策略（`TEMPLATE_CACHE`）。只有 `rootDesc.xml` 使用模板变量；SCPD 文件是静态的但仍通过 Jinja2 渲染。

## 辅助函数

| 函数 | 说明 |
|---|---|
| `get_local_ip()` | 通过 `socket.connect()` 到 `10.255.255.255:1` 发现本地 IP。失败时回退到 `127.0.0.1`。 |
| `get_local_port()` | 返回 `Config.LISTEN_PORT`。 |
| `get_location()` | 返回 `http://{ip}:{port}/rootDesc.xml`。 |

## 后台服务

`init_background_services()` 在应用启动时运行：

| 服务 | 说明 |
|---|---|
| SSDP 响应器 | 定期发送 `ssdp:alive` NOTIFY 通告（每 `Config.SSDP_NOTIFY_INTERVAL` 秒）。 |
| 租期清理 | 扫描所有服务中已过期的租期（每 `Config.LEASE_CLEANUP_INTERVAL` 秒），删除过期条目。 |
| STUN 客户端 | 若 `Config.STUN` 启用，启动 STUN 刷新线程以获取外网 IP。 |

`shutdown_background_services()` 发送 SSDP `ssdp:byebye` 通知并等待 SSDP 线程结束。

## 入口点

`main()` — 直接 Python 执行：调用 `setup_logging()`、配置信号处理、调用 `init_background_services()`、在 `0.0.0.0:{LISTEN_PORT}` 上运行 Flask 开发服务器、退出时调用 `shutdown_background_services()`。

## 健康检查

`GET /health` 返回 JSON，包含：
- `status`：`"healthy"` 或 `"degraded"`（取决于 GOST API 连通性）
- `gost_connected`：布尔值
- `port_mappings_count`：整数
- `local_ip`、`local_port`、`gost_api`、`version`

## WSGI

模块级别设置 `application = app`，用于 gunicorn/uvicorn ASGI-wrapped 服务。见 `gunicorn_config.py`。

# alter_upnpd - PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-26

## OVERVIEW
UPnP IGD (Internet Gateway Device) 前端网关，将 UPnP 端口转发 SOAP 请求转换为 GOST REST API 调用。
Python 3.11 + Flask，无外部数据库依赖。

让不支持 SOCKS/HTTP 代理的旧软件（miniupnpc、Transmission、qBittorrent）通过 GOST 建立端口映射。

## STRUCTURE
```
alter_upnpd/
├── app/                     # 主程序
│   ├── docker.sh            # Alpine 容器入口脚本（容器环境初始化）
│   ├── app.py               # Flask 路由 + 入口点 + 后台服务生命周期 + PyWebIO WebUI
│   ├── config.py            # 环境变量配置类
│   ├── gost_client.py       # GOST API CRUD 客户端（异常+重试+缓存+租赁过期）
│   ├── ssdp_responder.py    # SSDP 发现协议（端口 1900，多播）
│   ├── stun_client.py       # STUN 外网 IP 发现（py3stun）
│   ├── upstream_client.py   # 上游 IGD 客户端（端口映射同步）
│   ├── upnp_soap.py         # SOAP 动作处理器（ACL+IPConn+CIC+L3F）
│   ├── webui.py             # PyWebIO + ECharts 监控仪表板（路由 /）
│   ├── echarts_check.py     # ECharts CDN 版本校验
│   ├── static_bp.py         # 本地静态资源 Flask Blueprint
│   ├── static/              # 本地静态文件（echarts.min.js）
│   ├── gunicorn_config.py   # WSGI 生命周期钩子
│   └── xml/                 # UPnP 设备描述模板（Jinja2）
│       ├── rootDesc.xml
│       ├── L3F.xml
│       ├── WANCfg.xml
│       └── WANIPCn.xml
├── test/                    # 测试（161+ 用例）
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_gost_client.py
│   ├── test_stun.py
│   ├── test_upnp_soap.py
│   └── test_webui.py
├── docs/                    # 文档（中英双语）
│   ├── agents/              # Agent 技能配置  ##不要公开与项目开发无关内容
│   ├── upnp-compliance-audit.md  # UPnP 规范合规审计报告
│   ├── app.md / app.zh.md
│   ├── config.md / config.zh.md
│   ├── gost_client.md / gost_client.zh.md
│   ├── gunicorn_config.md / gunicorn_config.zh.md
│   ├── handoff.md / handoff.zh.md
│   ├── ssdp_responder.md / ssdp_responder.zh.md
│   ├── stun_client.md / stun_client.zh.md
│   └── upnp_soap.md / upnp_soap.zh.md
├── docker-compose.yml       # 编排部署（gost + alter_upnpd + python_test）
├── .env.example
├── .gitignore
├── AGENTS.md
├── requirements.txt
└── README.md
```

## WHERE TO LOOK
| Task | Location |
|------|-----------|
| 配置项 | config.py → `Config` 类 |
| 添加端口转发 | upnp_soap.py → `_handle_add_port_mapping` |
| 删除端口转发 | upnp_soap.py → `_handle_delete_port_mapping` |
| 按索引/协议查询端口映射 | upnp_soap.py → `_handle_get_port_mapping_entry` / `_handle_get_specific_port_mapping` |
| GOST API 增删改 | gost_client.py → `add_port_mapping` / `update_port_mapping` / `delete_port_mapping` |
| GOST API 查询 | gost_client.py → `get_port_mappings` / `get_port_mapping_by_index` / `has_port_mapping` |
| 租赁过期清理 | gost_client.py → `get_expired_services` / app.py → `run_lease_cleanup` |
| STUN 外网 IP | stun_client.py → `init()` / `get_wan_ip()` |
| 上游 IGD 同步 | upstream_client.py → `init()` / `add_port_mapping()` / `delete_port_mapping()` |
| SSDP NOTIFY 公告 | ssdp_responder.py → `SSDPResponder._send_alive` / `_send_byebye` |
| SSDP M-SEARCH 响应 | ssdp_responder.py → `SSDPHandler._send_search_response` |
| SOAP 路由入口 | app.py → `/ctl/IPConn`, `CmnIfCfg`, `L3F`, `WANPPPCn` |
| 健康检查 | app.py → `/health` |
| WebUI 仪表板 | webui.py → `main()` |
| 表格渲染 | webui.py → `_render_table()` |
| 流量图表 | webui.py → `_build_echarts_html()` |
| 批量删除 | webui.py → `_delete_selected()` |
| WSGI 生命周期 | gunicorn_config.py → `on_starting`, `post_worker_init`, `worker_exit` |

## CONVENTIONS
- 路由使用 `app.route()` 装饰器注册
- SOAP 处理使用 `@soap_action` 装饰器注册（`upnp_soap.py`）
- XML 使用 Jinja2 模板渲染，缓存按 mtime 失效
- 配置通过 `config.Config` 类（从环境变量读取）
- `GostClient` 有内部缓存 (`_services_cache`)，增删改操作后自动清空缓存
- 异常体系：`GostConnectionError`（网络层） / `GostApiError`（HTTP 层）

## API ROUTES

| 路径 | 方法 | 说明 | 处理器 |
|---|---|---|---|
| `/rootDesc.xml` | GET | 根设备描述 | `render_xml("rootDesc.xml")` |
| `/WANIPCn.xml` | GET | WANIPConnection SCPD | `render_xml("WANIPCn.xml")` |
| `/L3F.xml` | GET | Layer3Forwarding SCPD | `render_xml("L3F.xml")` |
| `/WANCfg.xml` | GET | WANCommonInterfaceConfig SCPD | `render_xml("WANCfg.xml")` |
| `/ctl/IPConn` | POST | 端口映射 SOAP 操作 | `soap_handler.handle_wanipconnection()` |
| `/ctl/WANPPPCn` | POST | WANPPPConnection（同 IPConn） | `soap_handler.handle_wanipconnection()` |
| `/ctl/CmnIfCfg` | POST | 接口配置查询 | `soap_handler.handle_wancommonifconfig()` |
| `/ctl/L3F` | POST | 转发服务配置 | `soap_handler.handle_l3forwarding()` |
| `/health` | GET | 健康检查 JSON | 返回状态/版本/GOST 连接/映射数 |
| `/` | GET/POST | WebUI 仪表板 | `webio_view(webui_main)` — PyWebIO 全功能 UI |

## UPnP IMPLEMENTATION STATUS

### WANIPConnection:1（核心 — 端口映射）
| Action | 状态 |
|---|---|
| `AddPortMapping` | ✅ 完整 |
| `DeletePortMapping` | ✅ 完整（404 无害） |
| `GetGenericPortMappingEntry` | ✅ 完整 |
| `GetSpecificPortMappingEntry` | ✅ 完整 |
| `GetExternalIPAddress` | ✅ 完整（STUN + fallback） |
| `GetStatusInfo` | ⚠️ 占位值 |
| `GetNATRSIPStatus` | ⚠️ 硬编码 true |
| `SetConnectionType` / `GetConnectionTypeInfo` | ✅ IP_Routed |
| `ForceTermination` / `RequestConnection` | ⚠️ 空操作 |
| `DeletePortMappingRange` / `GetListOfPortMappings` | ❌ 可选未实现 |

### WANCommonInterfaceConfig:1
| Action | 状态 |
|---|---|
| `GetCommonLinkProperties` | ⚠️ 硬编码值 |
| `GetTotalBytes*` / `GetTotalPackets*` | ⚠️ 返回 0 |

### Layer3Forwarding:1
| Action | 状态 |
|---|---|
| `GetDefaultConnectionService` | ⚠️ 默认 UDN |
| `SetDefaultConnectionService` | ⚠️ 忽略参数 |

### SSDP
| 特性 | 状态 |
|---|---|
| NOTIFY alive (周期性) | ✅ 每 180s 可配 |
| NOTIFY byebye | ✅ 退出时发送 |
| M-SEARCH 响应 | ✅ ST 匹配正确 |
| BOOTID/CONFIGID/SEARCHPORT | ⚠️ 缺失，非必需 |

完整合规审计见 `docs/upnp-compliance-audit.md`。

## COMMANDS
```bash
# 开发运行
cd /data/alter_upnpd/app && python3 app.py

# 测试
cd /data/alter_upnpd && pytest test/ -v

# Docker 部署
docker compose up -d gost alter_upnpd
```

## CONFIGURATION

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GOST_API_URL` | `http://127.0.0.1:8000` | GOST API 基础地址 |
| `LISTEN_PORT` | `5000` | HTTP 监听端口（默认 5000，避免与 GOST API 端口冲突） |
| `DEBUG` | `false` | 调试日志开关 |
| `ACL_ENABLED` | `true` | IP 访问控制 |
| `SECURE_MODE` | `true` | 安全模式：阻止跨 IP 映射和删除他人映射 |
| `ACL_ALLOWED_SUBNETS` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 允许的子网 |
| `SSDP_NOTIFY_INTERVAL` | `180` | SSDP 公告间隔（秒） |
| `STUN` | `true` | 启用 STUN 外网探测 |
| `STUN_SERVER` | `stun.l.google.com:19302` | STUN 服务器 |
| `LEASE_DURATION` | `604800` | 租赁时长上限（秒） |
| `LEASE_CLEANUP_INTERVAL` | `60` | 过期清理间隔（秒） |
| `UPSTREAM_IGD_URL` | `""` | 上游 IGD rootDesc.xml URL（空=禁用） |
| `GOST_WEBUI_REFRESH_INTERVAL` | `10` | WebUI 刷新间隔（秒） |
| `GOST_WEBUI_HISTORY_POINTS` | `8640` | 每端口存储的数据点上限 |
| `GOST_METRICS_URL` | `""` | Prometheus metrics URL（空则自动发现） |

## NOTES
- SSDP 使用 `ssdp` 库（不是 Flask-Evil-SSDP 重构）
- STUN 通过 `py3stun` 库实现，默认启用
- 支持 upnpc 命令：`-a` 添加, `-d` 删除, `-r` 查询, `-l` 列表, `-s` 状态
- 路由 `/ctl/WANPPPCn` 与 `/ctl/IPConn` 共享同一处理器
- GostClient 内置重试（3 次）和缓存，缓存增删改操作后自动失效
- gunicorn_config.py 生命周期钩子管理 SSDP/租赁清理线程
- upstream_client.py 通过 `UPSTREAM_IGD_URL` 配置上游 IGD 的 rootDesc.xml URL，自动发现 WANIPConnection 控制端点
- 上游 IGD 不可达时静默降级——不影响下游 GOST 映射的正常使用
- WebUI 仪表板通过 PyWebIO `webio_view` 注册到 Flask 路由 `/`，ECharts 从本地 `/static/echarts.min` 加载
- WebUI 使用 GostClient 实例获取实时数据，后台线程每 10 秒增量刷新

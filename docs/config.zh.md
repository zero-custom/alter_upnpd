# config.py — 配置

## 架构

`config.py` 分为三个区：

| 区 | 内容 | 使用方式 |
|---|---|---|
| **PART 1: EnvConfig** | 环境变量配置（18 个字段） | 应用启动时 `load_env_config()` 构造一次。EnvConfig 实例留在 `app.py` 内，各模块所需的值通过构造函数参数传入。 |
| **PART 2: 分组常量** | 硬编码可调参数，按所属模块分组 | 各模块只 import 自己的组：`from config import GostClientConfig`，然后 `GostClientConfig.REQUEST_TIMEOUT` 直接使用 |
| **PART 3: 参考表** | 定义在各模块内部的常量 | 仅供查阅。需修改时直接编辑对应源文件。 |

## 模块分组（PART 2）

各模块导入自己的组，直接使用：

```python
# gost_client.py
from config import GostClientConfig
# GostClientConfig.REQUEST_TIMEOUT  → 10
# GostClientConfig.RETRIES          → 2

# ssdp_responder.py
from config import SsdpConfig
# SsdpConfig.CACHE_CONTROL  → 1800
# SsdpConfig.SERVER_ID      → "Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0"

# stun_client.py
from config import StunConfig
# StunConfig.RETRIES             → 4
# StunConfig.REFRESH_INTERVAL    → 86400
# StunConfig.FALLBACK_WAN_IP     → "192.0.2.1"

# app.py
from config import AppConfig
# AppConfig.SHUTDOWN_TIMEOUT  → 5
# AppConfig.VERSION           → "1.3.1"
```

## 环境变量（PART 1）

| 变量 | EnvConfig 字段 | 默认值 | 说明 |
|---|---|---|---|
| `GOST_API_URL` | `gost_api_url` | `http://127.0.0.1:8000` | GOST REST API 的基础 URL。 |
| `LISTEN_PORT` | `listen_port` | `5000` | Flask HTTP 服务的监听端口。 |
| `DEBUG` | `debug` | `false` | 启用 debug 级别日志。 |
| `ACL_ENABLED` | `acl_enabled` | `true` | 为 SOAP 端点启用基于 IP 的访问控制。 |
| `SECURE_MODE` | `secure_mode` | `true` | 阻止 AddPortMapping 将端口映射到非请求者 IP；阻止 DeletePortMapping 删除他人映射。 |
| `ACL_ALLOWED_SUBNETS` | `acl_allowed_subnets` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 允许发送 SOAP 请求的 CIDR 子网列表（逗号分隔）。 |
| `SSDP_NOTIFY_INTERVAL` | `ssdp_notify_interval` | `180` | SSDP `ssdp:alive` NOTIFY 多播公告的间隔（秒）。 |
| `STUN` | `stun` | `true` | 启用启动时的 STUN 外网 IP 发现。 |
| `STUN_SERVER` | `stun_server` | `stun.l.google.com:19302` | STUN 服务器地址（host:port，用于外网 IP 发现）。 |
| `LEASE_DURATION` | `lease_duration` | `604800` | 端口映射的默认租期（秒）。上限为 604800（7 天）。 |
| `LEASE_CLEANUP_INTERVAL` | `lease_cleanup_interval` | `60` | 过期租期清理扫描的间隔（秒）。 |
| `UPSTREAM_IGD_URL` | `upstream_igd_url` | `""` | 上游 UPnP IGD 的 rootDesc.xml URL。设置后 AddPortMapping / DeletePortMapping 会自动同步至上游 IGD（失败时静默降级，不影响下游映射）。 |
| `UPSTREAM_INTERNAL_HOST` | `upstream_internal_host` | `""` | 同步端口映射到上游 IGD 时，覆写 `NewInternalClient` 字段。空 = 让上游 IGD 自动填入 SOAP 请求来源 IP。 |
| `GOST_API_USERNAME` | `gost_api_username` | `""` | GOST API Basic Auth 用户名（需同时设置用户名和密码才生效）。 |
| `GOST_API_PASSWORD` | `gost_api_password` | `""` | GOST API Basic Auth 密码。 |
| `GOST_METRICS_URL` | `gost_metrics_url` | `""` | Prometheus metrics URL，用于实时带宽/连接统计。空 = 从 GOST API `/metrics` 端点自动发现。 |
| `GOST_WEBUI_REFRESH_INTERVAL` | `gost_webui_refresh_interval` | `10` | 仪表板刷新间隔（秒）。 |
| `GOST_WEBUI_HISTORY_POINTS` | `gost_webui_history_points` | `8640` | 每端口存储的流量图表数据点上限。 |

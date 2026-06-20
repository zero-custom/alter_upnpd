# config.py — 配置

通过环境变量进行全局配置，以 `Config` 类的类属性暴露。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GOST_API_URL` | `http://127.0.0.1:8000` | GOST REST API 的基础 URL。 |
| `LISTEN_PORT` | `5000` | Flask HTTP 服务的监听端口。 |
| `DEBUG` | `false` | 启用 debug 级别日志。 |
| `ACL_ENABLED` | `true` | 为 SOAP 端点启用基于 IP 的访问控制。 |
| `SECURE_MODE` | `true` | 阻止 AddPortMapping 将端口映射到非请求者 IP；阻止 DeletePortMapping 删除他人映射。 |
| `ACL_ALLOWED_SUBNETS` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 允许发送 SOAP 请求的 CIDR 子网列表（逗号分隔）。 |
| `SSDP_NOTIFY_INTERVAL` | `180` | SSDP `ssdp:alive` NOTIFY 多播公告的间隔（秒）。 |
| `STUN` | `true` | 启用启动时的 STUN 外网 IP 发现。 |
| `STUN_SERVER` | `stun.l.google.com:19302` | STUN 服务器地址（host:port，用于外网 IP 发现）。 |
| `LEASE_DURATION` | `604800` | 端口映射的默认租期（秒）。上限为 604800（7 天）。 |
| `LEASE_CLEANUP_INTERVAL` | `60` | 过期租期清理扫描的间隔（秒）。 |
| `UPSTREAM_IGD_URL` | `""` | 上游 UPnP IGD 的 rootDesc.xml URL。设置后 AddPortMapping / DeletePortMapping 会自动同步至上游 IGD（失败时静默降级，不影响下游映射）。 |
| `UPSTREAM_INTERNAL_HOST` | `""` | 同步端口映射到上游 IGD 时，覆写 `NewInternalClient` 字段。空 = 让上游 IGD 自动填入 SOAP 请求来源 IP。 |
| `GOST_API_USERNAME` | `""` | GOST API Basic Auth 用户名（需同时设置用户名和密码才生效）。 |
| `GOST_API_PASSWORD` | `""` | GOST API Basic Auth 密码。 |
| `GOST_REQUEST_TIMEOUT` | `10` | GOST API HTTP 请求超时（秒）。 |
| `GOST_RETRIES` | `2` | GOST API 连接/超时错误的重试次数（指数退避）。 |

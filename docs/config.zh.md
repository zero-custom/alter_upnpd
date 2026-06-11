# config.py — 配置

通过环境变量进行全局配置，以 `Config` 类的类属性暴露。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GOST_API_URL` | `http://127.0.0.1:8000` | GOST REST API 的基础 URL。 |
| `LISTEN_PORT` | `8000` | Flask HTTP 服务的监听端口。 |
| `DEBUG` | `false` | 启用 debug 级别日志。 |
| `ACL_ENABLED` | `true` | 为 SOAP 端点启用基于 IP 的访问控制。 |
| `ACL_ALLOWED_SUBNETS` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 允许发送 SOAP 请求的 CIDR 子网列表（逗号分隔）。 |
| `SSDP_NOTIFY_INTERVAL` | `180` | SSDP `ssdp:alive` NOTIFY 多播公告的间隔（秒）。 |
| `STUN` | `true` | 启用启动时的 STUN 外网 IP 发现。 |
| `STUN_SERVER` | `stun.l.google.com:19302` | STUN 服务器地址（host:port，用于外网 IP 发现）。 |
| `LEASE_DURATION` | `604800` | 端口映射的默认租期（秒）。上限为 604800（7 天）。 |
| `LEASE_CLEANUP_INTERVAL` | `60` | 过期租期清理扫描的间隔（秒）。 |

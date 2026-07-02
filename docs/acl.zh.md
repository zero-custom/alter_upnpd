# acl.py — UPnP 访问控制与安全模式

基于 IP 子网过滤和安全模式的端口映射操作控制。无 Flask 依赖——纯逻辑代码，使用 `ipaddress` 标准库。

## ACLEnforcer

对传入的 UPnP 控制请求执行 IP 白名单过滤和安全模式约束检查。

### 构造参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `enabled` | `True` | IP 子网过滤总开关。 |
| `secure_mode` | `True` | 阻止客户端映射到非自身 IP 或删除他人的映射。 |
| `allowed_subnets` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 逗号分隔的 CIDR 子网列表。 |

### 方法

| 方法 | 返回值 | 说明 |
|---|---|---|
| `check_request(remote_ip)` | `None` 或拒绝原因 | 如果 IP 在允许的子网中则放行。无效 IP 记录警告。 |
| `check_port_mapping(remote_ip, internal_client, existing_client)` | `None` 或拒绝原因 | 安全模式检查：客户端不能映射到不同 IP；不能删除他人的映射。 |

### 检查流程

```
check_request()
  └─ 已禁用 → None（允许）
  └─ IP 在 allowed_subnets 中 → None（允许）
  └─ IP 不在 allowed_subnets 中 → "Forbidden: IP ..."

check_port_mapping()
  └─ secure_mode 已禁用 → None（允许）
  └─ internal_client != remote_ip → "SECURE: cannot map to ..."
  └─ existing_client != remote_ip → "SECURE: cannot delete ..."
  └─ 所有检查通过 → None（允许）
```

### 配置

构造参数来自 `EnvConfig`（通过 `app.py` 传入）：`EnvConfig.acl_enabled`、`EnvConfig.secure_mode`、`EnvConfig.acl_allowed_subnets`。

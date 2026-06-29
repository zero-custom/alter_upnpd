# acl.py — UPnP ACL & Secure Mode Enforcement

IP subnet filtering and secure-mode enforcement for port mapping operations. No Flask dependency — pure logic with `ipaddress` stdlib.

## ACLEnforcer

Validates incoming UPnP control requests against IP allowlists and secure-mode constraints.

### Constructor

| Param | Default | Description |
|---|---|---|
| `enabled` | `True` | Master switch for IP subnet filtering. |
| `secure_mode` | `True` | Prevents clients from mapping to a different IP or deleting others' mappings. |
| `allowed_subnets` | `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | Comma-separated CIDR subnets. |

### Methods

| Method | Returns | Description |
|---|---|---|
| `check_request(remote_ip)` | `None` or reason string | Allows if IP is in any allowed subnet. Logs warning on invalid IP. |
| `check_port_mapping(remote_ip, internal_client, existing_client)` | `None` or reason string | Secure-mode checks: client cannot map to a different IP; client cannot delete another's mapping. |

### Flow

```
check_request()
  └─ disabled → None (allowed)
  └─ IP in allowed_subnets → None (allowed)
  └─ IP not in allowed_subnets → "Forbidden: IP ..."

check_port_mapping()
  └─ secure_mode disabled → None (allowed)
  └─ internal_client != remote_ip → "SECURE: cannot map to ..."
  └─ existing_client != remote_ip → "SECURE: cannot delete ..."
  └─ all checks pass → None (allowed)
```

### Configuration

Controlled via `Config.ACL_ENABLED`, `Config.SECURE_MODE`, and `Config.ACL_ALLOWED_SUBNETS`.

# upstream_client.py — 上游 IGD 端口映射同步

通过 miniupnpc 向上游 UPnP IGD 转发端口映射操作，实现双层 NAT 下端口映射的穿透传播。

## 拓扑

```
上游 IGD:  ext:8888 ──►  (SOAP 请求来源 IP) :8888
GOST:      :8888    ──►  client_ip:9000
```

`NewInternalClient` 刻意留空——上游 IGD（99% 是 miniupnpd）通过其 `#ifndef UPNP_STRICT` 回退机制自动填入 SOAP 请求的源 IP。这避免了对本地 IP 探测（socket / `u.lanaddr`）的依赖。

## 调用流程

`UPSTREAM_IGD_URL` 的检查发生在**调用方**（`upnp_soap.py`），而非本模块内部：

```
upnp_soap.py:
    if Config.UPSTREAM_IGD_URL:
        upstream_client.add_port_mapping(...)
```

本模块是纯执行者——不决定是否应该转发。

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `UPSTREAM_IGD_URL` | `""` | 上游 IGD 的 rootDesc.xml URL。空 = 禁用。 |

## 函数

| 函数 | 可见性 | 说明 |
|---|---|---|
| `add_port_mapping(...)` | 公开 | 转发 AddPortMapping 到上游 IGD。首次调用时惰性初始化。失败不阻塞。 |
| `delete_port_mapping(...)` | 公开 | 转发 DeletePortMapping 到上游 IGD。首次调用时惰性初始化。失败不阻塞。 |
| `_ensure_upnp()` | 私有 | 惰性初始化器：创建 miniupnpc 客户端，连接到 `UPSTREAM_IGD_URL`。首次 `add_port_mapping` / `delete_port_mapping` 时自动调用。 |

## 行为

- **惰性初始化**：miniupnpc 客户端在首次实际端口映射调用时创建，而非导入或启动时。
- **静默降级**：上游失败仅记 warning，不影响 GOST 侧映射。
- **NewInternalClient**：刻意留空。上游 IGD（miniupnpd 默认编译）自动填入 SOAP 请求来源 IP——即 alter_upnpd 宿主机。
- **映射对称**：上游映射使用与 GOST 映射相同的外部端口。

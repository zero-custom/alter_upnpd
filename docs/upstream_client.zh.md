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
    if EnvConfig.upstream_igd_url:
        upstream_client.add_port_mapping(...)
```

本模块是纯执行者——不决定是否应该转发。

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `UPSTREAM_IGD_URL` | `""` | 上游 IGD 的 rootDesc.xml URL。空 = 禁用。 |
| `UPSTREAM_INTERNAL_HOST` | `""` | 同步端口映射到上游 IGD 时，覆写 `NewInternalClient` 字段。空 = 让上游 IGD 自动填入 SOAP 请求来源 IP。 |

## 函数

| 函数 | 可见性 | 说明 |
|---|---|---|
| `add_port_mapping(...)` | 公开 | 转发 AddPortMapping 到上游 IGD。首次调用时惰性初始化。失败不阻塞。 |
| `delete_port_mapping(...)` | 公开 | 转发 DeletePortMapping 到上游 IGD。首次调用时惰性初始化。失败不阻塞。 |
| `_ensure_upnp()` | 私有 | 惰性初始化器：创建 miniupnpc 客户端，连接到 `UPSTREAM_IGD_URL`。首次 `add_port_mapping` / `delete_port_mapping` 时自动调用。 |
| `_ensure_upnp_connected()` | 私有 | 连接健康检查。调用 `getportmappingnumberofentries()` 作为心跳；连接失效时销毁旧连接并重新执行 `_ensure_upnp()`。返回 `bool`。 |
| `list_mappings()` | 公开 | 通过 `getgenericportmapping(i)` 循环枚举上游 IGD 上所有端口映射。返回 `list[dict]`。仅用于调试/审计——不在生产路径中使用。 |
| `reconcile(gost_mappings)` | 公开 | 对比每个 GOST 管理的映射与上游 IGD，恢复缺失的映射。返回 `(restored, failed)`。详见 Reconcile 流程。 |

## Reconcile 流程

Reconcile 解决上游 IGD 映射丢失问题（如 IGD 重启）。在租期清理线程中每 `LEASE_CLEANUP_INTERVAL`（默认 60s）执行一次。

### 策略：方案 B（按需查询）

```
for each GOST mapping:
    getspecificportmapping(ext_port, proto)
    → None?      → addportmapping(...)   # 缺失 → 恢复
    → returns tuple? → continue           # 已存在
```

### 连接健康检查

```
reconcile()
  → _ensure_upnp_connected()
      → self._upnp exists?
          → getportmappingnumberofentries()     # 心跳 SOAP
              ✓ → return True
              ✗ → self._upnp = None, 继续向下
      → _ensure_upnp()                          # 重新 selectigd
          → miniupnpc.UPnP()
          → selectigd(self._igd_url)            # HTTP GET rootDesc.xml，不经过 SSDP
          ✓ → self._upnp = u
          ✗ → self._upnp 保持 None → reconcile 返回 (0, 0)
```

- `selectigd(url)` 调用 `UPNP_GetIGDFromUrl()`——直接 HTTP GET，从不 SSDP `upnpDiscover()`
- 如果心跳失败，旧连接被销毁，通过配置的 `UPSTREAM_IGD_URL` 建立新连接
- 如果重新连接失败，reconcile 静默返回 (0, 0) 并在下一周期重试

### 故障隔离

| 故障 | 影响 |
|---|---|
| 心跳 `getportmappingnumberofentries()` 失败 | 重新建立连接；重新连接也失败则跳过本次 reconcile |
| 单个 `getspecificportmapping()` 失败 | 该映射标记为 `failed`，继续处理下一个 |
| 单个 `addportmapping()` 失败 | 该映射标记为 `failed`，继续处理下一个 |

## 行为

- **惰性初始化**：miniupnpc 客户端在首次实际端口映射调用时创建，而非导入或启动时。
- **静默降级**：上游失败仅记 warning，不影响 GOST 侧映射。
- **NewInternalClient**：默认留空，上游 IGD（miniupnpd 默认编译）自动填入 SOAP 请求来源 IP——即 alter_upnpd 宿主机。设置 `UPSTREAM_INTERNAL_HOST` 可覆写 `NewInternalClient` 值，用于需要指定不同内部主机地址的场景。
- **映射对称**：上游映射使用与 GOST 映射相同的外部端口。
- **连接重建**：仅 `reconcile()` 主动检测连接失效并触发重新连接。`add_port_mapping()` / `delete_port_mapping()` 记录失败但不触发重新连接——依赖下一周期 reconcile 恢复连接。

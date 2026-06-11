# stun_client.py — STUN 外网 IP 解析

通过 STUN 协议发现 WAN（外网）IP 地址。使用模块级函数（非类）。后台线程在启动时解析 IP，之后每 24 小时刷新一次。

## 函数

### `init()`

启动后台刷新守护线程。幂等——重复调用不会重复启动。当 `Config.STUN` 启用时，由 `app.init_background_services()` 调用。

### `get_wan_ip() -> str`

返回最近发现的外网 IP。线程安全（使用锁保护）。回退值为 `1.2.3.4`。

### `reset_cache()`

将 WAN IP 重置为 `1.2.3.4`，允许 `init()` 重新启动新线程。用于测试。

## 刷新流程

1. 从 `Config.STUN_SERVER`（格式 `host:port`）解析 STUN 服务器地址。
2. 调用 `py3stun.get_ip_info()`，最多重试 `_STUN_RETRIES`（4）次。
3. 成功时：保存外网 IP，记录成功日志。
4. 失败时（所有重试用尽）：保留之前的值，记录警告日志。
5. 休眠 `_REFRESH_INTERVAL`（86400 秒 = 24 小时），然后从第 1 步重复。

## 与 SOAP 处理器的集成

`GetExternalIPAddress` SOAP 动作在 `Config.STUN` 启用时调用 `stun_client.get_wan_ip()`。禁用时返回静态回退值 `1.2.3.4`。

# alter_upnpd — Handoff（中文）

## 已完成的工作

### 1. AGENTS.md 创建与完善
- 编写初始 `AGENTS.md`，包含架构、目录结构、SOAP 注册表、命令、测试、环境变量、反模式、SSDP 常量。
- 根据反馈迭代完善：添加关键事实、修正 XML 文件描述、澄清 SOAP 注册表结构、添加已知限制章节。

### 2. 中文文档（`.zh.md`）
- 为全部 7 个源文档文件创建中文版本（`*.zh.md`），与英文版（`.md`）并列存放：
  - `app`、`config`、`gost_client`、`gunicorn_config`、`ssdp_responder`、`stun_client`、`upnp_soap`
- 决定：同时保留 `.md`（英文）和 `.zh.md`（中文）作为兄弟文件，不互相覆盖。

### 3. Handoff 文档
- 在 `docs/` 中创建 `handoff.md`（英文）和 `handoff.zh.md`（中文），用于会话连续性。

## 项目状态
- 三个 SOAP 注册表：`SOAP_ACTIONS`（WANIPConnection）、`CIC_ACTIONS`（WANCommonInterfaceConfig）、`L3F_ACTIONS`（Layer3Forwarding）。
- `AGENTS.md`、`.env.example` 和所有程序文档已清理就绪。
- 保留之前会话的工作（metadata lease、lease cap、TTL 缓存、P0/P1/P2 修复、命名空间修复、SSDP 完成）。

## 关键文件
- `alter_upnpd/AGENTS.md` — 纯项目 agent 指南
- `alter_upnpd/docs/` — 14 个程序文档文件（7 英文 + 7 中文）+ 2 个 handoff 文件
- `alter_upnpd/app/` — 7 个 Python 源文件 + xml/ 目录

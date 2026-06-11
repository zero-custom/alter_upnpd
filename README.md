# alter_upnpd

**UPnP IGD 前端网关** — 将 UPnP 端口转发 SOAP 请求转换为 GOST REST API 调用。

Python + Flask，无外部数据库依赖。

通过模拟 UPnP 互联网网关设备 (IGD)，方便应用通过 UPNP 协议建立端口映射。

## Application Setup

`alter_upnpd` 监听 HTTP 端口（默认 5000），向局域网内 UPnP 客户端提供设备发现（SSDP）和端口映射管理（SOAP）服务。所有端口映射操作通过 GOST REST API 执行，不直接操作 iptables。

```text
UPnP 客户端 (miniupnpc/Transmission/qBittorrent)
    │ SSDP 发现 + SOAP 控制
    ▼
alter_upnpd  ──HTTP──►  GOST API
    │                    │
    │                    ▼
    │              实际端口转发 (relay/tunnel)
    │
    └── SSDP (设备发现广播)
```

### 本地开发

```bash
pip install -r requirements.txt
cp .env.example .env
cd app && python3 app.py
```

### UPnP 客户端使用

UPnP 客户端通过 SSDP 自动发现 alter_upnpd，或直接指定设备描述 URL：

```bash
# 自动发现（SSDP 多播）
upnpc -l

# 指定设备 URL
upnpc -l -u http://host.docker.internal:5000/rootDesc.xml
```

## Usage

### docker-compose

```yaml
services:
  gost:
    image: gogost/gost:latest
    network_mode: host
    restart: unless-stopped
    command: ["-api", ":8000"]

  alter_upnpd:
    image: zerocustom/alter_upnpd:latest
    restart: unless-stopped
    depends_on:
      - gost
    ports:
      - 5000:5000    #端口映射非必须
    environment:
      - GOST_API_URL=http://host.docker.internal:8000
      - LISTEN_PORT=5000
      - ACL_ENABLED=true
      - ACL_ALLOWED_SUBNETS=172.16.0.0/12
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### docker cli

```bash
docker run -d \
  --name=alter_upnpd \
  -p 5000:5000    #端口映射非必须\
  -e GOST_API_URL=http://host.docker.internal:8000 \
  -e LISTEN_PORT=5000 \
  -e ACL_ENABLED=true \
  -e ACL_ALLOWED_SUBNETS=172.16.0.0/12 \
  --add-host host.docker.internal:host-gateway \
  --restart unless-stopped \
  zerocustom/alter_upnpd:latest
```

> GOST 需要 `network_mode: host` 或独立部署。`host.docker.internal` 用于容器内连接宿主机上的 GOST 服务。

## Parameters

| Parameter | Function |
| :----: | --- |
| `-p 5000:5000` | HTTP 服务端口（SOAP + 设备描述 + 健康检查） |
| `-e GOST_API_URL=http://host.docker.internal:8000` | GOST API 地址 |
| `-e LISTEN_PORT=5000` | HTTP 监听端口，须与端口映射一致 |
| `-e DEBUG=false` | 开启调试日志 |
| `-e ACL_ENABLED=true` | IP 访问控制开关 |
| `-e ACL_ALLOWED_SUBNETS=192.168.0.0/16,10.0.0.0/8,172.16.0.0/12` | 允许的客户端子网（逗号分隔） |
| `-e STUN=true` | 启用 STUN 外网 IP 探测 |
| `-e STUN_SERVER=stun.l.google.com:19302` | STUN 服务器地址 |
| `-e LEASE_DURATION=604800` | 端口映射租约上限（秒） |
| `-e LEASE_CLEANUP_INTERVAL=60` | 过期清理间隔（秒） |
| `-e SSDP_NOTIFY_INTERVAL=180` | SSDP 公告间隔（秒） |

### 引导脚本 docker.sh

容器入口为 `docker.sh`，支持以下环境变量吗，可以在**不修改镜像**的前提下安装额外包：

| Parameter | Function |
| :----: | --- |
| `-e INSTALL_PACKAGES=` | Alpine apk 包列表，`\|` 分隔，如 `miniupnpc\|curl` |
| `-e INSTALL_PIP_PACKAGES=` | pip 包列表，`\|` 分隔，如 `Flask\|gunicorn\|requests` |
| `-e PACKAGES_MIRROR=` | Alpine apk 镜像源，如 `mirrors.tencent.com` |
| `-e PIP_MIRROR=` | pip 镜像源，如 `https://mirrors.tencent.com/pypi/simple` |

## Support Info

查看容器日志：

```bash
docker logs -f alter_upnpd
```

进入容器：

```bash
docker exec -it alter_upnpd sh
```

查看健康状态：

```bash
curl http://localhost:5000/health
```

## Building locally

```bash
git clone <your-repo-url> alter_upnpd
cd alter_upnpd
docker build -t zerocustom/alter_upnpd:latest .
```

## Project Structure

```
├── app/                     # 主程序
│   ├── docker.sh            # 容器引导脚本
│   ├── app.py               # Flask 路由 + 入口点
│   ├── config.py            # 全局配置集中管理
│   ├── gost_client.py       # GOST API CRUD 客户端
│   ├── ssdp_responder.py    # SSDP 发现协议（端口 1900）
│   ├── stun_client.py       # STUN 外网 IP 发现
│   ├── upnp_soap.py         # SOAP 动作处理器
│   ├── gunicorn_config.py   # WSGI 配置
│   └── xml/                 # UPnP 设备描述模板
├── test/                    # 测试
├── docs/                    # 文档
├── Dockerfile               # 生产镜像构建
└── docker-compose.yml       # 编排部署
```

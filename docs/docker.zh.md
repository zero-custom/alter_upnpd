# docker.sh — Alpine 容器入口脚本

Alpine 容器（`python:alpine`）的入口点脚本，在执行业务 CMD 之前完成镜像源配置和包安装。

专为默认包仓库访问缓慢或不可达的环境设计。`docker-compose.yml` 中 `alter_upnpd` 和 `python_test` 服务均使用此脚本。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PACKAGES_MIRROR` | 空 | APK 镜像主机名（如 `mirrors.tencent.com`）。将 `dl-cdn.alpinelinux.org` 替换为指定镜像。 |
| `PIP_MIRROR` | 空 | PyPI 镜像 URL（如 `https://mirrors.tencent.com/pypi/simple`）。传给 `pip install -i`。 |
| `INSTALL_PACKAGES` | 空 | 需安装的 Alpine 包，管道符分隔（例：`miniupnpc\|curl`）。 |
| `INSTALL_PIP_PACKAGES` | 空 | 需安装的 Python 包，管道符分隔（例：`Flask\|gunicorn\|requests`）。 |

## 执行流程

1. **APK 镜像源** — 若设置了 `PACKAGES_MIRROR`，将 `/etc/apk/repositories` 中的默认源替换为镜像地址。
2. **APK 包安装** — 若设置了 `INSTALL_PACKAGES`，通过 `apk add --no-cache` 安装。
3. **Python 引导** — 若设置了 `INSTALL_PIP_PACKAGES` 但未找到 `python3`，先通过 APK 安装 `python3` + `py3-pip`。
4. **PIP 包安装** — 若设置了 `INSTALL_PIP_PACKAGES`，逐个检查：如已可导入则跳过，否则 `pip install`（使用配置的镜像源）。
5. **`exec "$@"`** — 用容器 CMD 替换当前 shell 进程。

## docker-compose.yml 使用示例

```yaml
alter_upnpd:
  image: python:alpine
  entrypoint: ["/app/docker.sh"]
  command: ["gunicorn", "-c", "gunicorn_config.py", "app:application"]
  environment:
    - PACKAGES_MIRROR=mirrors.tencent.com
    - PIP_MIRROR=https://mirrors.tencent.com/pypi/simple
    - INSTALL_PIP_PACKAGES=Flask|gunicorn|requests|lxml|ssdp|py3stun
```

## 说明

- 包列表使用管道符 `|` 分隔，以兼容 Docker Compose 的 `environment` 平铺列表格式。
- 每个 PIP 包通过 `__import__()` 检查是否已安装，容器重启后不会重复安装。
- 传递 `--break-system-packages` 和 `--root-user-action ignore` 给 pip，因为容器以 root 运行在一次性环境中。
- 若需要 `python3` 但安装失败，脚本返回退出码 1。

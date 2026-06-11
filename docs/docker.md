# docker.sh — Alpine Container Entrypoint

Entrypoint script for Alpine-based Docker containers (`python:alpine`). Handles package installation with mirror support before executing the container's `CMD`.

Designed for environments where default package registries are slow or unreachable. Used by both the `alter_upnpd` and `python_test` services in `docker-compose.yml`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PACKAGES_MIRROR` | *(empty)* | APK mirror hostname (e.g. `mirrors.tencent.com`). Replaces `dl-cdn.alpinelinux.org` in `/etc/apk/repositories`. |
| `PIP_MIRROR` | *(empty)* | PyPI mirror URL (e.g. `https://mirrors.tencent.com/pypi/simple`). Passed as `-i` to `pip install`. |
| `INSTALL_PACKAGES` | *(empty)* | Alpine packages to install, pipe-separated (e.g. `miniupnpc\|curl`). |
| `INSTALL_PIP_PACKAGES` | *(empty)* | Python packages to install, pipe-separated (e.g. `Flask\|gunicorn\|requests`). |

## Flow

1. **APK mirror** — If `PACKAGES_MIRROR` is set, replace the default mirror in `/etc/apk/repositories`.
2. **APK packages** — If `INSTALL_PACKAGES` is set, install via `apk add --no-cache`.
3. **Python bootstrap** — If `INSTALL_PIP_PACKAGES` is set but `python3` is not found, install `python3` + `py3-pip` via APK first.
4. **PIP packages** — If `INSTALL_PIP_PACKAGES` is set, iterate each package: skip if already importable, otherwise `pip install` with the configured mirror.
5. **`exec "$@"`** — Replace the shell process with the container `CMD`.

## Usage in docker-compose.yml

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

## Notes

- Package lists use pipe (`|`) as separator to stay compatible with Docker Compose's flat `environment` list format.
- Each PIP package is individually checked via `__import__()` before installation — idempotent across container restarts.
- `--break-system-packages` and `--root-user-action ignore` are passed to `pip` because the container runs as root inside a disposable environment.
- If `python3` is required but couldn't be installed, the script exits with code 1.

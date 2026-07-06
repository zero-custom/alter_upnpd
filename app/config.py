import os
import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvConfig:
    listen_port: int = 5000
    debug: bool = False

    acl_enabled: bool = True
    secure_mode: bool = True
    acl_allowed_subnets: str = "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12"

    ssdp_notify_interval: int = 180

    stun: bool = True
    stun_server: str = "stun.l.google.com:19302"

    lease_duration: int = 604800
    lease_cleanup_interval: int = 60

    upstream_igd_url: str = ""
    upstream_internal_host: str = ""

    gost_webui_refresh_interval: int = 10
    gost_webui_history_points: int = 8640

    gost_api_url: str = "http://127.0.0.1:8000"
    gost_api_username: str = ""
    gost_api_password: str = ""
    gost_metrics_url: str = ""

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        fields = []
        for f in dataclasses.fields(self):
            val = getattr(self, f.name)
            if "password" in f.name.lower() or "secret" in f.name.lower():
                val = "******" if val else ""
            fields.append(f"{f.name}={val!r}")
        return f"{cls}({', '.join(fields)})"


def load_env_config() -> EnvConfig:
    return EnvConfig(
        listen_port=int(os.environ.get("LISTEN_PORT", "5000")),
        debug=os.environ.get("DEBUG", "false").lower() == "true",
        acl_enabled=os.environ.get("ACL_ENABLED", "true").lower() == "true",
        secure_mode=os.environ.get("SECURE_MODE", "true").lower() == "true",
        acl_allowed_subnets=os.environ.get(
            "ACL_ALLOWED_SUBNETS",
            "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12",
        ),
        ssdp_notify_interval=int(os.environ.get("SSDP_NOTIFY_INTERVAL", "180")),
        stun=os.environ.get("STUN", "true").lower() == "true",
        stun_server=os.environ.get("STUN_SERVER", "stun.l.google.com:19302"),
        lease_duration=int(os.environ.get("LEASE_DURATION", "604800")),
        lease_cleanup_interval=int(os.environ.get("LEASE_CLEANUP_INTERVAL", "60")),
        upstream_igd_url=os.environ.get("UPSTREAM_IGD_URL", ""),
        upstream_internal_host=os.environ.get("UPSTREAM_INTERNAL_HOST", ""),
        gost_webui_refresh_interval=int(
            os.environ.get("GOST_WEBUI_REFRESH_INTERVAL", "10")
        ),
        gost_webui_history_points=int(
            os.environ.get("GOST_WEBUI_HISTORY_POINTS", "8640")
        ),
        gost_api_url=os.environ.get("GOST_API_URL", "http://127.0.0.1:8000"),
        gost_api_username=os.environ.get("GOST_API_USERNAME", ""),
        gost_api_password=os.environ.get("GOST_API_PASSWORD", ""),
        gost_metrics_url=os.environ.get("GOST_METRICS_URL", ""),
    )


class GostClientConfig:
    REQUEST_TIMEOUT = 10
    RETRIES = 2


class SsdpConfig:
    CACHE_CONTROL = 1800
    SERVER_ID = "Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0"


class StunConfig:
    RETRIES = 4
    REFRESH_INTERVAL = 86400
    FALLBACK_WAN_IP = "192.0.2.1"


class GunicornConfig:
    WORKERS = 1
    TIMEOUT = 30
    GRACEFUL_TIMEOUT = 10
    KEEPALIVE = 5


class AppConfig:
    SHUTDOWN_TIMEOUT = 5
    VERSION = "1.3.2"


# ═══════════════════════════════════════════════════════
# 模块内部常量参考（仅文档，不可通过 config.py 修改）
# ═══════════════════════════════════════════════════════
# gunicorn_config.py:   workers = 1, timeout = 30, graceful_timeout = 10, keepalive = 5
# ssdp_responder.py:    USN = "uuid:ed8d683a-...", MCAST_GROUP = "239.255.255.250", SSDP_PORT = 1900
# upnp_soap.py:         PORT_MIN = 1, PORT_MAX = 65535, MAX_SOAP_BODY = 102400
# webui.py:             _PREFIXES = ("B", "KB", "MB", "GB", "TB"), _COLORS = ("success", ...)

import os


class Config:
    # ── HTTP ──
    LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "5000"))
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # ── ACL ──
    ACL_ENABLED = os.environ.get("ACL_ENABLED", "true").lower() == "true"
    SECURE_MODE = os.environ.get("SECURE_MODE", "true").lower() == "true"
    ACL_ALLOWED_SUBNETS = os.environ.get(
        "ACL_ALLOWED_SUBNETS",
        "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12",
    )

    # ── SSDP ──
    SSDP_NOTIFY_INTERVAL = int(os.environ.get("SSDP_NOTIFY_INTERVAL", "180"))

    # ── STUN ──
    STUN = os.environ.get("STUN", "true").lower() == "true"
    STUN_SERVER = os.environ.get("STUN_SERVER", "stun.l.google.com:19302")

    # ── Lease ──
    LEASE_DURATION = int(os.environ.get("LEASE_DURATION", "604800"))
    LEASE_CLEANUP_INTERVAL = int(os.environ.get("LEASE_CLEANUP_INTERVAL", "60"))

    # ── Upstream IGD ──
    UPSTREAM_IGD_URL = os.environ.get("UPSTREAM_IGD_URL", "")
    UPSTREAM_INTERNAL_HOST = os.environ.get("UPSTREAM_INTERNAL_HOST", "")

    # ── WebUI ──
    GOST_WEBUI_REFRESH_INTERVAL = int(os.environ.get("GOST_WEBUI_REFRESH_INTERVAL", "10"))
    GOST_WEBUI_HISTORY_POINTS = int(os.environ.get("GOST_WEBUI_HISTORY_POINTS", "8640"))

    # ── GOST Client ──
    GOST_API_URL = os.environ.get("GOST_API_URL", "http://127.0.0.1:8000")
    GOST_API_USERNAME = os.environ.get("GOST_API_USERNAME", "")
    GOST_API_PASSWORD = os.environ.get("GOST_API_PASSWORD", "")
    GOST_METRICS_URL = os.environ.get("GOST_METRICS_URL", "")

    # ── Internal constants (not env-configurable) ──
    GOST_REQUEST_TIMEOUT = 10
    GOST_RETRIES = 2
    SSDP_CACHE_CONTROL = 1800
    SERVER_ID = "Linux/2.6.18 UPnP/1.1 alter_upnpd/1.0"
    STUN_RETRIES = 4
    STUN_REFRESH_INTERVAL = 86400
    FALLBACK_WAN_IP = "192.0.2.1"
    VERSION = "1.2.0"
    SHUTDOWN_TIMEOUT = 5
    WSGI_WORKERS = 1
    WSGI_TIMEOUT = 30
    WSGI_GRACEFUL_TIMEOUT = 10
    WSGI_KEEPALIVE = 5

import logging
from typing import Any, Callable

from gost_client import GostClient

logger = logging.getLogger("alter_upnpd.health")


class HealthService:
    def __init__(
        self,
        gost_client: GostClient,
        version: str,
        get_local_ip: Callable[[], str],
        get_local_port: Callable[[], int],
    ):
        self._gost = gost_client
        self._version = version
        self._get_local_ip = get_local_ip
        self._get_local_port = get_local_port

    def check(self) -> dict[str, Any]:
        gost_ok = self._gost.is_available()

        if gost_ok:
            mappings = self._gost.get_port_mappings()
            mappings_count = len(mappings)
            status = "healthy"
        else:
            mappings_count = 0
            status = "degraded"
            logger.warning("GOST API unreachable, health check degraded")

        return {
            "status": status,
            "version": self._version,
            "local_ip": self._get_local_ip(),
            "local_port": self._get_local_port(),
            "gost_api": self._gost.base_url,
            "gost_connected": gost_ok,
            "port_mappings_count": mappings_count,
        }

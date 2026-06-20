import base64
import logging
import time
from typing import Any, Optional, List, Dict

import requests

from config import Config

logger = logging.getLogger("alter_upnpd.gost_client")


class GostConnectionError(Exception):
    pass


class GostApiError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


def _pluck_services(data: dict) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for key, val in data.items():
        if isinstance(val, dict):
            if any(k in val for k in ("addr", "handler", "forwarder")):
                svc = dict(val)
                svc.setdefault("name", key)
                items.append(svc)
            else:
                nested = _pluck_services(val)
                items.extend(nested)
        elif isinstance(val, list):
            items.extend(s for s in val if isinstance(s, dict))
    return items


class GostClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.timeout = Config.GOST_REQUEST_TIMEOUT
        self._services_cache: Optional[List[Dict[str, Any]]] = None
        self._services_cache_ts: float = 0
        self._services_cache_ttl: int = 30

    # ── Connectivity ──

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/config/services", timeout=5)
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False

    # ── Port-mapping helpers ──

    def has_port_mapping(self, external_port: int, protocol: str = "tcp") -> bool:
        mappings = self.get_port_mappings()
        proto = protocol.lower()
        for m in mappings:
            if m["external_port"] == external_port and m["protocol"].lower() == proto:
                return True
        return False

    def get_expired_services(self) -> List[Dict[str, Any]]:
        now = time.time()
        expired: List[Dict[str, Any]] = []
        for svc in self.get_services():
            meta = svc.get("metadata", {}) or {}
            if not meta.get("upnp"):
                continue
            created_at = meta.get("created_at")
            lease_duration = meta.get("lease_duration", 0)
            if lease_duration > 0 and created_at is not None:
                if now >= created_at + lease_duration:
                    expired.append({
                        "service_name": svc.get("name", ""),
                        "external_port": meta.get("external_port", 0),
                        "protocol": meta.get("protocol", "tcp"),
                    })
        return expired

    # ── Low-level HTTP ──

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        max_retries = Config.GOST_RETRIES

        if Config.GOST_API_USERNAME and Config.GOST_API_PASSWORD:
            credentials = f"{Config.GOST_API_USERNAME}:{Config.GOST_API_PASSWORD}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers = kwargs.setdefault("headers", {})
            headers.setdefault("Authorization", f"Basic {encoded}")

        for attempt in range(max_retries + 1):
            try:
                resp = requests.request(method, url, timeout=self.timeout, **kwargs)
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise GostConnectionError(str(e)) from e
            except requests.exceptions.Timeout as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise GostConnectionError(str(e)) from e
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 500
                body = e.response.text[:200] if e.response is not None else ""
                logger.warning("GOST API HTTP %d: %s", status, body)
                raise GostApiError(f"{e} body={body}", status) from e
            except requests.exceptions.RequestException as e:
                raise GostConnectionError(str(e)) from e
            except ValueError as e:
                raise GostApiError(f"Invalid response: {e}") from e

        raise GostConnectionError("Max retries exceeded")

    # ── Service read ──

    def get_services(self) -> List[Dict[str, Any]]:
        now = time.time()
        if self._services_cache is not None and now - self._services_cache_ts < self._services_cache_ttl:
            return self._services_cache
        self._services_cache = None
        try:
            result = self._request("GET", "/config/services")
            self._services_cache = self._extract_services(result)
            self._services_cache_ts = time.time()
            return self._services_cache
        except (GostConnectionError, GostApiError):
            return []

    @staticmethod
    def _extract_services(result: Any) -> List[Dict[str, Any]]:
        if isinstance(result, list):
            return [s for s in result if isinstance(s, dict)]

        if not isinstance(result, dict):
            logger.warning("Unexpected GOST response type: %s", type(result).__name__)
            return []

        for key in ("data", "services", "result", "items"):
            val = result.get(key)
            if isinstance(val, list):
                return [s for s in val if isinstance(s, dict)]
            if isinstance(val, dict):
                extracted = _pluck_services(val)
                if extracted:
                    return extracted

        logger.info("GOST response keys %s — no service list found, code=%s",
                     list(result.keys()), result.get("code"))
        return []

    # ── Port-mapping CRUD ──

    def add_port_mapping(
        self,
        external_port: int,
        internal_port: int,
        internal_client: str,
        protocol: str = "tcp",
        description: str = "",
        remote_host: str = "",
        enabled: bool = True,
        lease_duration: int = 0,
    ) -> Dict[str, Any]:
        proto_lower = protocol.lower()
        service_name = f"upnp_{external_port}_{proto_lower}"

        service_config = {
            "name": service_name,
            "addr": f":{external_port}",
            "handler": {"type": proto_lower},
            "listener": {"type": proto_lower},
            "metadata": {
                "upnp": True,
                "external_port": external_port,
                "internal_port": internal_port,
                "internal_client": internal_client,
                "protocol": proto_lower,
                "description": description,
                "remote_host": remote_host,
                "enabled": enabled,
                "lease_duration": lease_duration,
                "created_at": int(time.time()),
            },
            "forwarder": {
                "nodes": [
                    {
                        "name": f"node_{external_port}_{proto_lower}",
                        "addr": f"{internal_client}:{internal_port}",
                    }
                ]
            },
        }

        logger.info(
            "Adding port mapping: %s/%s -> %s:%s  service=%s  lease=%s",
            protocol, external_port, internal_client, internal_port,
            service_name, lease_duration,
        )

        result = self._request("POST", "/config/services", json=service_config)
        self._services_cache = None
        logger.info(
            "Port mapping added: %s/%s (lease=%s)", protocol, external_port, lease_duration
        )
        return result

    def update_port_mapping(
        self,
        external_port: int,
        internal_port: int,
        internal_client: str,
        protocol: str = "tcp",
        description: str = "",
        remote_host: str = "",
        enabled: bool = True,
        lease_duration: int = 0,
    ) -> Dict[str, Any]:
        proto_lower = protocol.lower()
        service_name = f"upnp_{external_port}_{proto_lower}"

        service_config = {
            "name": service_name,
            "addr": f":{external_port}",
            "handler": {"type": proto_lower},
            "listener": {"type": proto_lower},
            "metadata": {
                "upnp": True,
                "external_port": external_port,
                "internal_port": internal_port,
                "internal_client": internal_client,
                "protocol": proto_lower,
                "description": description,
                "remote_host": remote_host,
                "enabled": enabled,
                "lease_duration": lease_duration,
                "created_at": int(time.time()),
            },
            "forwarder": {
                "nodes": [
                    {
                        "name": f"node_{external_port}_{proto_lower}",
                        "addr": f"{internal_client}:{internal_port}",
                    }
                ]
            },
        }

        logger.info(
            "Updating port mapping: %s/%s -> %s:%s  service=%s  lease=%s",
            protocol, external_port, internal_client, internal_port,
            service_name, lease_duration,
        )

        result = self._request("PUT", f"/config/services/{service_name}", json=service_config)
        self._services_cache = None
        logger.info(
            "Port mapping updated: %s/%s (lease=%s)", protocol, external_port, lease_duration
        )
        return result

    def delete_port_mapping(self, external_port: int, protocol: str = "tcp") -> Dict[str, Any]:
        service_name = f"upnp_{external_port}_{protocol}"
        logger.info(
            "Deleting port mapping: %s/%s  service=%s",
            protocol, external_port, service_name,
        )

        try:
            self._request("DELETE", f"/config/services/{service_name}")
            self._services_cache = None
            logger.info("Service deleted: %s", service_name)
        except GostApiError as e:
            if e.status_code != 404:
                raise
            self._services_cache = None
            logger.warning("Service not found (already deleted): %s", service_name)

        return {"code": 0, "msg": "Port mapping deleted"}

    def get_port_mappings(self) -> List[Dict[str, Any]]:
        services = self.get_services()
        mappings: List[Dict[str, Any]] = []

        for svc in services:
            meta = svc.get("metadata", {}) or {}
            if not meta.get("upnp"):
                continue

            remaining = 0
            created_at = meta.get("created_at")
            lease_duration = meta.get("lease_duration", 0)
            if lease_duration > 0 and created_at is not None:
                remaining = max(0, int(created_at + lease_duration - time.time()))

            mappings.append({
                "remote_host": meta.get("remote_host", ""),
                "external_port": meta.get("external_port", 0),
                "protocol": meta.get("protocol", "tcp").upper(),
                "internal_port": meta.get("internal_port", 0),
                "internal_client": meta.get("internal_client", ""),
                "description": meta.get("description", ""),
                "enabled": meta.get("enabled", True),
                "lease_duration_remaining": remaining,
            })

        return mappings

    def get_port_mapping_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        mappings = self.get_port_mappings()
        if 0 <= index < len(mappings):
            return mappings[index]

    def get_port_mapping_by_port(self, external_port: int, protocol: str = "tcp") -> Optional[Dict[str, Any]]:
        mappings = self.get_port_mappings()
        proto = protocol.lower()
        for m in mappings:
            if m["external_port"] == external_port and m["protocol"].lower() == proto:
                return m
        return None
        return None

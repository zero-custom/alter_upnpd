import base64
import logging
import time
from typing import Any, Optional, List, Dict, Tuple
from urllib.parse import urlparse

import requests
from prometheus_client.parser import text_string_to_metric_families

from config import Config

logger = logging.getLogger("alter_upnpd.gost_client")


class GostConnectionError(Exception):
    pass


class GostApiError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.status_code = status_code
        super().__init__(message)


class MetricsFilter:
    def __init__(self, service: Optional[str] = None):
        self.service = service

    def matches(self, labels: Dict[str, str]) -> bool:
        if self.service is not None:
            if labels.get("service") != self.service:
                return False
        return True


class PrometheusMetrics:
    """Parsed Prometheus metrics snapshot."""

    def __init__(self) -> None:
        self.counters: Dict[str, List[Tuple[Dict[str, str], float]]] = {}
        self.gauges: Dict[str, List[Tuple[Dict[str, str], float]]] = {}
        self.histograms: Dict[str, List[Tuple[Dict[str, str], float]]] = {}
        self.text_raw: str = ""

    @classmethod
    def parse(cls, text: str) -> "PrometheusMetrics":
        pm = cls()
        pm.text_raw = text
        for family in text_string_to_metric_families(text):
            if family.type == "counter":
                for sample in family.samples:
                    base = sample.name
                    if base.endswith("_total"):
                        base = base[:-6]
                    pm.counters.setdefault(base, []).append((sample.labels, sample.value))
            elif family.type in ("gauge", "untyped"):
                for sample in family.samples:
                    pm.gauges.setdefault(sample.name, []).append((sample.labels, sample.value))
            elif family.type in ("histogram", "summary"):
                for sample in family.samples:
                    pm.histograms.setdefault(sample.name, []).append((sample.labels, sample.value))
        return pm

    def sum_counter(self, name: str, flt: Optional[MetricsFilter] = None) -> float:
        total = 0.0
        for labels, value in self.counters.get(name, []):
            if flt is None or flt.matches(labels):
                total += value
        return total

    def sum_gauge(self, name: str, flt: Optional[MetricsFilter] = None) -> float:
        total = 0.0
        for labels, value in self.gauges.get(name, []):
            if flt is None or flt.matches(labels):
                total += value
        return total

    def first_gauge(self, name: str) -> float:
        items = self.gauges.get(name, [])
        return items[0][1] if items else 0.0


class SpeedTracker:
    def __init__(self) -> None:
        self._snapshots: Dict[str, Dict[str, int]] = {}
        self._last_time: float = 0

    def update(self, mappings: List[Dict]) -> None:
        now = time.time()
        elapsed = now - self._last_time if self._last_time > 0 else 0

        for m in mappings:
            name = m["name"]
            prev = self._snapshots.get(name)
            cur_in = m.get("input_bytes", 0)
            cur_out = m.get("output_bytes", 0)

            if prev and elapsed > 0:
                m["speed_in"] = max(0, (cur_in - prev["input_bytes"]) / elapsed)
                m["speed_out"] = max(0, (cur_out - prev["output_bytes"]) / elapsed)
            else:
                m["speed_in"] = 0.0
                m["speed_out"] = 0.0

            self._snapshots[name] = {"input_bytes": cur_in, "output_bytes": cur_out}

        self._last_time = now


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
        self.base_url = base_url.rstrip("/")
        self.timeout = Config.GOST_REQUEST_TIMEOUT
        self._services_cache: Optional[List[Dict[str, Any]]] = None
        self._services_cache_ts: float = 0
        self._services_cache_ttl: int = 15
        self._config_cache: Optional[Dict[str, Any]] = None
        self._config_cache_ts: float = 0
        self._config_cache_ttl: int = 60
        self._metrics_url: Optional[str] = None
        self._speed_tracker = SpeedTracker()

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

    def _invalidate_cache(self) -> None:
        self._services_cache = None
        self._services_cache_ts = 0

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
        name = f"upnp_{external_port}_{proto_lower}"

        service_config = {
            "name": name,
            "addr": f":{external_port}",
            "handler": {"type": proto_lower},
            "listener": {"type": proto_lower},
            "metadata": {
                "upnp": True,
                "enableStats": "true",
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
            name, lease_duration,
        )

        result = self._request("POST", "/config/services", json=service_config)
        self._invalidate_cache()
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
                "enableStats": "true",
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
        self._invalidate_cache()
        logger.info(
            "Port mapping updated: %s/%s (lease=%s)", protocol, external_port, lease_duration
        )
        return result

    def delete_port_mapping(
        self,
        external_port: int,
        protocol: str = "tcp",
    ) -> Dict[str, Any]:
        service_name = f"upnp_{external_port}_{protocol.lower()}"

        logger.info("Deleting port mapping: %s/%s  service=%s", protocol, external_port, service_name)

        try:
            self._request("DELETE", f"/config/services/{service_name}")
            self._invalidate_cache()
            logger.info("Service deleted: %s", service_name)
        except GostApiError as e:
            if e.status_code != 404:
                raise
            self._invalidate_cache()
            logger.warning("Service not found (already deleted): %s", service_name)

        return {"code": 0, "msg": "Port mapping deleted"}

    def delete_port_mappings_batch(
        self,
        port_proto_list: List[Tuple[int, str]],
    ) -> Tuple[int, int]:
        success = 0
        failed = 0
        for port, proto in port_proto_list:
            try:
                self.delete_port_mapping(port, proto)
                success += 1
            except (GostConnectionError, GostApiError) as e:
                logger.warning("Failed to delete %d/%s: %s", port, proto, e)
                failed += 1
        self._invalidate_cache()
        return success, failed

    def get_port_mappings(self) -> List[Dict[str, Any]]:
        services = self.get_services()
        mappings: List[Dict[str, Any]] = []

        for svc in services:
            meta = svc.get("metadata", {}) or {}
            if not meta.get("upnp"):
                continue

            name = svc.get("name", "")
            status = svc.get("status", {}) or {}
            stats = status.get("stats", {}) or {}
            state = status.get("state", "")
            created_at = meta.get("created_at")
            lease_duration = meta.get("lease_duration", 0)

            remaining = 0
            if lease_duration > 0 and created_at is not None:
                remaining = max(0, int(created_at + lease_duration - time.time()))

            display_name = meta.get("description", "") or name

            mappings.append({
                "name": name,
                "display_name": display_name,
                "remote_host": meta.get("remote_host", ""),
                "external_port": meta.get("external_port", 0),
                "protocol": meta.get("protocol", "tcp").upper(),
                "internal_client": meta.get("internal_client", ""),
                "internal_port": meta.get("internal_port", 0),
                "description": meta.get("description", ""),
                "enabled": meta.get("enabled", True),
                "lease_duration": lease_duration,
                "lease_duration_remaining": remaining,
                "has_stats": bool(stats),
                "state": state,
                "current_conns": stats.get("currentConns", 0),
                "total_conns": stats.get("totalConns", 0),
                "input_bytes": stats.get("inputBytes", 0),
                "output_bytes": stats.get("outputBytes", 0),
                "total_errs": stats.get("totalErrs", 0),
                "lease_remaining": remaining,
                "speed_in": 0.0,
                "speed_out": 0.0,
            })

        self._speed_tracker.update(mappings)
        return mappings

    def get_port_mapping_count(self) -> int:
        return len(self.get_port_mappings())

    def get_port_mapping_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        mappings = self.get_port_mappings()
        if 0 <= index < len(mappings):
            return mappings[index]
        return None

    def get_port_mapping_by_port(self, external_port: int, protocol: str = "tcp") -> Optional[Dict[str, Any]]:
        mappings = self.get_port_mappings()
        proto = protocol.lower()
        for m in mappings:
            if m["external_port"] == external_port and m["protocol"].lower() == proto:
                return m
        return None

    # ── Config / Metrics ──

    def get_config(self) -> Dict[str, Any]:
        now = time.time()
        if self._config_cache is not None and now - self._config_cache_ts < self._config_cache_ttl:
            return self._config_cache
        result = self._request("GET", "/config")
        self._config_cache = result
        self._config_cache_ts = time.time()
        return result

    def discover_metrics_url(self) -> Optional[str]:
        if Config.GOST_METRICS_URL:
            self._metrics_url = Config.GOST_METRICS_URL
            return self._metrics_url

        try:
            config = self.get_config()
            mc = config.get("metrics", {})
            if not mc:
                logger.info("No metrics config found in GOST config")
                return None

            addr = mc.get("addr", "")
            path = mc.get("path", "/metrics")
            if not addr:
                return None

            if addr.startswith("unix:"):
                logger.info("Metrics via Unix socket, cannot fetch via HTTP")
                return None

            port: Optional[str] = None
            if addr.startswith(":"):
                port = addr[1:]
            elif ":" in addr:
                port = addr.rsplit(":", 1)[-1]

            if not port or not port.isdigit():
                return None

            parsed = urlparse(self.base_url)
            host = parsed.hostname or "localhost"
            scheme = parsed.scheme or "http"

            self._metrics_url = f"{scheme}://{host}:{port}{path}"
            logger.info("Discovered metrics URL: %s", self._metrics_url)
            return self._metrics_url
        except (GostConnectionError, GostApiError, Exception) as e:
            logger.warning("Failed to discover metrics URL: %s", e)
            return None

    def get_metrics_url(self) -> Optional[str]:
        if self._metrics_url is None:
            self.discover_metrics_url()
        return self._metrics_url

    def fetch_metrics(self) -> Optional[PrometheusMetrics]:
        url = self.get_metrics_url()
        if not url:
            return None

        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return PrometheusMetrics.parse(resp.text)
        except requests.exceptions.RequestException as e:
            logger.warning("Failed to fetch metrics from %s: %s", url, e)
            return None

    def get_summary_stats(self) -> Dict[str, Any]:
        """Return aggregated stats from Prometheus metrics."""
        pm = self.fetch_metrics()
        result: Dict[str, Any] = {
            "total_services": 0,
            "total_current_conns": 0,
            "total_input_bytes": 0,
            "total_output_bytes": 0,
            "total_requests": 0,
            "total_errors": 0,
            "available": False,
        }

        if pm is None:
            return result

        result["available"] = True
        result["total_services"] = int(pm.first_gauge("gost_services"))
        result["total_current_conns"] = int(
            pm.sum_gauge("gost_service_requests_in_flight")
        )
        result["total_input_bytes"] = int(
            pm.sum_counter("gost_service_transfer_input_bytes")
        )
        result["total_output_bytes"] = int(
            pm.sum_counter("gost_service_transfer_output_bytes")
        )
        result["total_requests"] = int(
            pm.sum_counter("gost_service_requests")
        )
        result["total_errors"] = int(
            pm.sum_counter("gost_service_handler_errors")
        )

        return result

    def get_all_services_stats(self) -> List[Dict[str, Any]]:
        """Aggregate currentConns from all services' status.stats."""
        services = self.get_services()
        stats_list: List[Dict[str, Any]] = []
        for svc in services:
            status = svc.get("status", {}) or {}
            stats = status.get("stats", {}) or {}
            if stats:
                stats_list.append({
                    "name": svc.get("name", ""),
                    "current_conns": stats.get("currentConns", 0),
                    "total_conns": stats.get("totalConns", 0),
                    "input_bytes": stats.get("inputBytes", 0),
                    "output_bytes": stats.get("outputBytes", 0),
                })
        return stats_list

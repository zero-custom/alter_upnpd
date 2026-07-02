import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from gost_client import GostClient, MetricsFilter, PrometheusMetrics

logger = logging.getLogger("alter_upnpd.gost_webui.format")

_PREFIXES = ("B", "KB", "MB", "GB", "TB")
_COLORS = ("success", "info", "warning", "danger")

_CHART_COLORS = {
    "speed_in": "#5470c6",
    "speed_out": "#91cc75",
    "current_conns": "#fc8452",
}
_CHART_NAMES = {
    "speed_in": "\u5165\u7ad9\u5e26\u5bbd",
    "speed_out": "\u51fa\u7ad9\u5e26\u5bbd",
    "current_conns": "\u8fde\u63a5\u6570",
}


@dataclass
class DataPoint:
    timestamp: float
    speed_in: float
    speed_out: float
    current_conns: int


@dataclass
class ChartState:
    history: Dict[str, List[DataPoint]] = field(default_factory=dict)
    chart_opts_queue: List[Tuple[str, str]] = field(default_factory=list)
    prev_total_input: int = 0
    prev_total_output: int = 0
    prev_total_time: float = 0
    max_history: int = 8640
    display_max: int = 8640


# ── Formatting ──


def _fmt_bytes(n: int) -> str:
    if n == 0:
        return "0B"
    value = float(n)
    for unit in _PREFIXES:
        if abs(value) < 1024:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}PB"


def _fmt_duration(sec: int) -> str:
    if sec <= 0:
        return "-"
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def _fmt_time(ts: float) -> str:
    t = time.localtime(ts)
    return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"


def _fmt_speed(bps: float) -> str:
    if bps <= 0:
        return ""
    value = float(bps)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if abs(value) < 1024:
            return f"{value:.1f}{unit}" if unit != "B/s" else f"{int(value)}B/s"
        value /= 1024
    return f"{value:.1f}PB/s"


# ── Downsample ──


def _downsample(points: List[DataPoint], max_points: Optional[int] = None) -> List[DataPoint]:
    if max_points is None:
        return points
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    return [points[int(i * step)] for i in range(max_points)]


# ── Record data points into ChartState ──


def _record_data_points(cs: ChartState, mappings: List[Dict], stats: Dict) -> None:
    now = time.time()

    def _append(key: str, dp: DataPoint) -> None:
        hist = cs.history.setdefault(key, [])
        hist.append(dp)
        if len(hist) > cs.max_history:
            hist[:] = hist[-cs.max_history:]

    for m in mappings:
        key = f"{m['protocol'].lower()}/{m['external_port']}"
        dp = DataPoint(
            timestamp=now,
            speed_in=m.get("speed_in", 0),
            speed_out=m.get("speed_out", 0),
            current_conns=m.get("current_conns", 0),
        )
        _append(key, dp)

    cur_input = stats.get("total_input_bytes", 0)
    cur_output = stats.get("total_output_bytes", 0)
    cur_conns = stats.get("total_current_conns", 0)

    if cs.prev_total_time > 0:
        elapsed = now - cs.prev_total_time
        speed_in = max(0, (cur_input - cs.prev_total_input) / elapsed) if elapsed > 0 else 0.0
        speed_out = max(0, (cur_output - cs.prev_total_output) / elapsed) if elapsed > 0 else 0.0
    else:
        speed_in = 0.0
        speed_out = 0.0

    cs.prev_total_input = cur_input
    cs.prev_total_output = cur_output
    cs.prev_total_time = now

    total_dp = DataPoint(now, speed_in, speed_out, cur_conns)
    _append("__total__", total_dp)


# ── Metrics aggregation ──


def get_summary_stats(
    client: GostClient,
    pm: Optional[PrometheusMetrics] = None,
) -> Dict[str, Any]:
    if pm is None:
        pm = client.fetch_metrics()
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


def get_all_services_stats(client: GostClient) -> List[Dict[str, Any]]:
    services = client.get_services()
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


# ── Summary data prep ──


def _prepare_summary_data(mappings: List[Dict], stats: Dict) -> List[Tuple[str, str, int]]:
    total = len(mappings)
    conns = stats.get("total_current_conns", 0)
    traffic = stats.get("total_input_bytes", 0) + stats.get("total_output_bytes", 0)
    errors = stats.get("total_errors", 0)
    avail = stats.get("available", False)
    return [
        ("PORT MAPPINGS", str(total), 1),
        ("ACTIVE CONNECTIONS", str(conns), 0),
        ("TOTAL TRAFFIC", _fmt_bytes(traffic) if avail else "-", 2),
        ("ERRORS", str(errors) if avail else "-", 3 if errors > 0 else 1),
    ]

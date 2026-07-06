import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pywebio import config
from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import defer_call, register_thread, run_js
from pywebio.exceptions import SessionNotFoundException

from gost_client import GostApiError, GostClient, GostConnectionError, MetricsFilter
from webui_format import (
    ChartState, DataPoint,
    _downsample, _fmt_bytes, _fmt_duration, _fmt_speed,
    _prepare_summary_data, _record_data_points,
    get_summary_stats,
)
import webui_render as render

logger = logging.getLogger("alter_upnpd.gost_webui")

_gost_client: Optional[GostClient] = None
_refresh_interval = 10
_REFRESH_LOCK = threading.Lock()

# 后台 collector：容器启动即开始采集，session 只读缓存
_collector_started = False
_collector_stop = threading.Event()
_collector_data_lock = threading.Lock()
_cached_mappings: List[Dict[str, Any]] = []
_cached_stats: Dict[str, Any] = {}


@dataclass
class SelectionState:
    selected_cache: Dict[str, Any] = field(default_factory=dict)
    prev_count: int = 0


@dataclass
class WebUIState:
    chart: ChartState = field(default_factory=ChartState)
    selection: SelectionState = field(default_factory=SelectionState)


_state = WebUIState()


def init(
    gost_client: GostClient,
    refresh_interval: int = 10,
    history_points: int = 8640,
):
    global _gost_client, _refresh_interval
    _gost_client = gost_client
    _refresh_interval = refresh_interval
    _state.chart.max_history = history_points
    _state.chart.display_max = min(history_points, 1000)


# ── Background collector (single writer) ──


def _start_background_collector() -> None:
    global _collector_started
    if _collector_started:
        return
    _collector_started = True
    if _collector_stop.is_set():
        _collector_stop.clear()
    t = threading.Thread(target=_collector_worker, daemon=True)
    t.start()
    logger.info("Background collector started")


def _collector_worker() -> None:
    while True:
        try:
            mappings = _gost_client.get_port_mappings()
            pm = _gost_client.fetch_metrics()

            # 用 Prometheus gost_service_requests_in_flight 覆盖 per-port current_conns
            if pm is not None:
                for m in mappings:
                    name = m["name"]
                    flt = MetricsFilter(service=name)
                    conns = pm.sum_gauge("gost_service_requests_in_flight", flt)
                    m["current_conns"] = int(conns)

            stats = get_summary_stats(_gost_client, pm=pm)

            with _collector_data_lock:
                _cached_mappings[:] = mappings
                _cached_stats.clear()
                _cached_stats.update(stats)

            _record_data_points(_state.chart, mappings, stats)
        except Exception:
            logger.exception("Background collector failed")

        if _collector_stop.wait(_refresh_interval):
            break


# ── Action handlers (callbacks from render layer) ──


def _handle_add() -> None:
    ext_port = pin["ext_port"]
    proto = pin["proto"]
    int_client = pin["int_client"]
    int_port = pin["int_port"]
    description = pin["desc"]
    lease = pin["lease"]

    if not ext_port:
        toast("External Port is required", color="error")
        return
    if not int_client:
        toast("Internal Client IP is required", color="error")
        return
    if not int_port:
        toast("Internal Port is required", color="error")
        return

    try:
        ext_val = int(ext_port)
        int_val = int(int_port)
    except ValueError:
        toast("Port must be a number", color="error")
        return

    if ext_val < 1 or ext_val > 65535:
        toast("External Port must be 1-65535", color="error")
        return
    if int_val < 1 or int_val > 65535:
        toast("Internal Port must be 1-65535", color="error")
        return

    try:
        _gost_client.add_port_mapping(
            external_port=ext_val,
            internal_port=int_val,
            internal_client=int_client.strip(),
            protocol=proto,
            description=description.strip(),
            lease_duration=int(lease or 0),
        )
        toast(f"Mapping added: {proto}/{ext_port} -> {int_client}:{int_port}", color="success")

        pin_update("ext_port", value="")
        pin_update("int_client", value="")
        pin_update("int_port", value="")
        pin_update("desc", value="")
        pin_update("lease", value=0)

        _refresh()
    except (GostConnectionError, GostApiError) as exc:
        toast(f"Failed: {exc}", color="error")
        logger.warning("Add mapping failed: %s", exc)


def _do_delete(action: str, ext_port: int, proto: str) -> None:
    if action != "delete":
        close_popup()
        return
    try:
        _gost_client.delete_port_mapping(ext_port, proto)
        toast(f"Deleted: {proto}/{ext_port}", color="info")
        close_popup()
        _refresh()
    except (GostConnectionError, GostApiError) as exc:
        toast(f"Delete failed: {exc}", color="error")
        logger.warning("Delete failed: %s", exc)
        close_popup()


def _delete_selected() -> None:
    try:
        mappings = _gost_client.get_port_mappings()
    except (GostConnectionError, GostApiError):
        toast("Failed to load mappings", color="error")
        return

    selected = []
    for m in mappings:
        ext_port = m.get("external_port")
        proto = m.get("protocol", "TCP").lower()
        cb_name = f"sel_{ext_port}_{proto}"
        try:
            val = pin[cb_name]
            if val:
                selected.append((int(ext_port), proto))
        except Exception:
            pass

    if not selected:
        toast("No items selected", color="warn")
        return

    with popup(f"Delete {len(selected)} mapping(s)?"):
        put_text(f"Delete {len(selected)} selected port mapping(s)?")
        put_buttons([
            dict(label="Delete", value="delete", color="danger"),
            dict(label="Cancel", value="cancel"),
        ], onclick=lambda v: _do_batch_delete(v, selected))


def _do_batch_delete(action: str, port_proto_list: List[Tuple[int, str]]) -> None:
    if action != "delete":
        close_popup()
        return
    success, failed = _gost_client.delete_port_mappings_batch(port_proto_list)
    close_popup()
    msg = f"Deleted: {success}"
    if failed:
        msg += f", Failed: {failed}"
    toast(msg, color="success" if not failed else "warn")
    _refresh()


def _on_confirm_delete(ext_port: int, proto: str) -> None:
    render._confirm_delete(ext_port, proto, lambda v, p, q: _do_delete(v, p, q))


# ── Update + refresh ──


def _update_table_data(mappings: List[Dict], stats: Dict) -> None:
    import json

    avail = stats.get("available", False)

    rows_data = []
    for m in mappings:
        ext_port = m.get("external_port", 0)
        proto = m.get("protocol", "TCP").lower()
        cb_name = f"sel_{ext_port}_{proto}"

        state_label = "ON" if m.get("enabled") else "OFF"
        state_color = "success" if m.get("enabled") else "secondary"
        conns = str(m.get("current_conns", 0)) if m.get("has_stats") else "-"
        lease = _fmt_duration(m.get("lease_remaining", 0))

        if m.get("has_stats"):
            traffic_in = _fmt_bytes(m.get("input_bytes", 0)) if avail else "-"
            traffic_out = _fmt_bytes(m.get("output_bytes", 0)) if avail else "-"
            si = _fmt_speed(m.get("speed_in", 0)) or "-"
            so = _fmt_speed(m.get("speed_out", 0)) or "-"
        else:
            traffic_in = "-"
            traffic_out = "-"
            si = "-"
            so = "-"

        rows_data.append({
            "cb": cb_name,
            "state": state_label,
            "sc": state_color,
            "conns": conns,
            "ti": traffic_in,
            "to": traffic_out,
            "si": si,
            "so": so,
            "lease": lease,
        })

    total_conns = str(stats.get("total_current_conns", 0))
    total_input = stats.get("total_input_bytes", 0)
    total_output = stats.get("total_output_bytes", 0)
    total_speed_in = sum(float(m.get("speed_in", 0)) for m in mappings)
    total_speed_out = sum(float(m.get("speed_out", 0)) for m in mappings)
    if avail:
        fti = _fmt_bytes(total_input)
        fto = _fmt_bytes(total_output)
        fsi = _fmt_speed(total_speed_in) or "-"
        fso = _fmt_speed(total_speed_out) or "-"
    else:
        fti = "-"
        fto = "-"
        fsi = "-"
        fso = "-"

    footer = {
        "conns": total_conns,
        "ti": fti,
        "to": fto,
        "si": fsi,
        "so": fso,
    }

    data_json = json.dumps(rows_data)
    footer_json = json.dumps(footer)
    run_js(render._build_table_update_js(data_json, footer_json))


def _refresh() -> None:
    if not _REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        with _collector_data_lock:
            mappings = list(_cached_mappings)
            stats = dict(_cached_stats)

        cs = _state.chart
        ss = _state.selection
        count_changed = len(mappings) != ss.prev_count
        ss.prev_count = len(mappings)

        render._render_summary(mappings, stats)

        render._render_charts(cs)

        if not mappings:
            render._render_table(cs, mappings, stats, _on_confirm_delete, _delete_selected)
        elif count_changed:
            ss.selected_cache.clear()
            for m in mappings:
                ext_port = m.get("external_port")
                proto = m.get("protocol", "TCP").lower()
                cb_name = f"sel_{ext_port}_{proto}"
                try:
                    if pin.get(cb_name, []):
                        ss.selected_cache[cb_name] = True
                except Exception:
                    pass

            render._render_table(cs, mappings, stats, _on_confirm_delete, _delete_selected)

            for cb_name in ss.selected_cache:
                try:
                    pin_update(cb_name, value=["selected"])
                except Exception:
                    pass
        else:
            _update_table_data(mappings, stats)
            run_js(render._build_per_port_data_update_js(cs))

        run_js(render._make_chart_js(cs))
    except SessionNotFoundException:
        logger.debug("Session closed - stopping refresh")
        raise
    except (GostConnectionError, GostApiError):
        logger.debug("Refresh skipped - GOST API unreachable")
    except Exception:
        logger.exception("Refresh failed")
    finally:
        cs.chart_opts_queue.clear()
        _REFRESH_LOCK.release()


# ── Entry point ──


def main() -> None:
    global _gost_client
    if _gost_client is None:
        from gost_client import GostClient
        _gost_client = GostClient("http://127.0.0.1:8000")
        logger.warning("webui.main() called without init() — using default GostClient")

    _start_background_collector()

    config(title="GOST Port Mapping Web UI", theme="yeti",
           css_style=render._CUSTOM_CSS)

    run_js(render._ECHARTS_CDN_JS)

    with _collector_data_lock:
        mappings = list(_cached_mappings)
        stats = dict(_cached_stats)

    # 冷启动兜底：collector 首次 fetch 还未完成时直接取一次
    if not mappings:
        try:
            mappings = _gost_client.get_port_mappings()
            stats = get_summary_stats(_gost_client)
            with _collector_data_lock:
                _cached_mappings[:] = mappings
                _cached_stats.clear()
                _cached_stats.update(stats)
        except (GostConnectionError, GostApiError):
            mappings = []
            stats = {}
            put_warning(
                "Cannot connect to GOST API - "
                "check that GOST is running and reachable."
            )

    _record_data_points(_state.chart, mappings, stats)
    _state.selection.prev_count = len(mappings)

    put_scope("summary")
    put_scope("charts")
    put_scope("table_area")
    put_scope("add_form")

    cs = _state.chart
    render._render_summary(mappings, stats)
    render._init_chart(cs)
    render._render_table(cs, mappings, stats, _on_confirm_delete, _delete_selected)
    run_js(render._make_chart_js(cs))
    render._render_add_form(on_add=_handle_add)

    _stop_refresh = threading.Event()

    def _refresh_worker():
        while not _stop_refresh.wait(_refresh_interval):
            try:
                _refresh()
            except SessionNotFoundException:
                logger.debug("Refresh worker exiting - session closed")
                break

    t = threading.Thread(target=_refresh_worker, daemon=True)
    register_thread(t)
    t.start()
    defer_call(lambda: _stop_refresh.set())

import logging
import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.commons.utils import JsCode
from pywebio import config
from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.session import defer_call, register_thread, run_js
from pywebio.exceptions import SessionNotFoundException

from config import Config
from gost_client import GostApiError, GostClient, GostConnectionError

logger = logging.getLogger("alter_upnpd.gost_webui")

client = GostClient(Config.GOST_API_URL)
_REFRESH_LOCK = threading.Lock()

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
    "current_conns": "\u8fde\u63a5\u6570"
}

_chart_opts_queue: List[Tuple[str, str]] = []

_ECHARTS_CDN_JS = (
    "require.config({paths:{'echarts':'/static/js/echarts.min'}});"
    "require(['echarts'],function(e){window.echarts=e;})"
)

@dataclass
class DataPoint:
    timestamp: float
    speed_in: float
    speed_out: float
    current_conns: int

_history: Dict[str, List[DataPoint]] = {}
_chart_keys_rendered: set = set()
_MAX_HISTORY = Config.GOST_WEBUI_HISTORY_POINTS
_DISPLAY_MAX = Config.GOST_WEBUI_HISTORY_POINTS

_prev_total_input: int = 0
_prev_total_output: int = 0
_prev_total_time: float = 0


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


def _card(label: str, value: str, color_idx: int) -> Any:
    return put_column([
        put_text(label).style(
            "color:#6c757d;font-size:.8rem;text-transform:uppercase;letter-spacing:.5px"
        ),
        put_text(value).style(
            f"font-size:2rem;font-weight:700;color:var(--bs-{_COLORS[color_idx]})"
        ),
    ]).style(
        "flex:1;background:#fff;border-radius:10px;"
        "padding:18px 14px;text-align:center;"
        "box-shadow:0 2px 8px rgba(0,0,0,.12);border:1px solid #e9ecef"
    )


def _render_summary(mappings: List[Dict], stats: Dict) -> None:
    with use_scope("summary", clear=True):
        total = len(mappings)
        conns = stats.get("total_current_conns", 0)
        traffic = stats.get("total_input_bytes", 0) + stats.get("total_output_bytes", 0)
        errors = stats.get("total_errors", 0)
        avail = stats.get("available", False)

        put_row([
            _card("PORT MAPPINGS", str(total), 1),
            _card("ACTIVE CONNECTIONS", str(conns), 0),
            _card("TOTAL TRAFFIC", _fmt_bytes(traffic) if avail else "-", 2),
            _card("ERRORS", str(errors) if avail else "-", 3 if errors > 0 else 1),
        ]).style("gap:16px;margin-bottom:16px")


def _record_data_points(mappings: List[Dict], stats: Dict) -> None:
    global _prev_total_input, _prev_total_output, _prev_total_time
    now = time.time()

    for m in mappings:
        key = f"{m['protocol'].lower()}/{m['external_port']}"
        dp = DataPoint(
            timestamp=now,
            speed_in=m.get("speed_in", 0),
            speed_out=m.get("speed_out", 0),
            current_conns=m.get("current_conns", 0),
        )
        hist = _history.setdefault(key, [])
        hist.append(dp)
        if len(hist) > _MAX_HISTORY:
            hist[:] = hist[-_MAX_HISTORY:]

    cur_input = stats.get("total_input_bytes", 0)
    cur_output = stats.get("total_output_bytes", 0)
    cur_conns = stats.get("total_current_conns", 0)

    if _prev_total_time > 0:
        elapsed = now - _prev_total_time
        speed_in = max(0, (cur_input - _prev_total_input) / elapsed) if elapsed > 0 else 0.0
        speed_out = max(0, (cur_output - _prev_total_output) / elapsed) if elapsed > 0 else 0.0
    else:
        speed_in = 0.0
        speed_out = 0.0

    _prev_total_input = cur_input
    _prev_total_output = cur_output
    _prev_total_time = now

    total_dp = DataPoint(now, speed_in, speed_out, cur_conns)
    hist = _history.setdefault("__total__", [])
    hist.append(total_dp)
    if len(hist) > _MAX_HISTORY:
        hist[:] = hist[-_MAX_HISTORY:]


def _downsample(points: List[DataPoint], max_points: int = _DISPLAY_MAX) -> List[DataPoint]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    return [points[int(i * step)] for i in range(max_points)]


def _build_echarts_html(chart_id: str, points: List[DataPoint], title: str = "", height: int = 220) -> str:
    if not points or len(points) < 2:
        return ""

    pts = _downsample(points)
    times = [_fmt_time(p.timestamp) for p in pts]
    data_in  = [round(p.speed_in, 1) for p in pts]
    data_out = [round(p.speed_out, 1) for p in pts]
    data_conns = [p.current_conns for p in pts]

    zoom_start = 0
    if len(pts) > 1:
        time_range = pts[-1].timestamp - pts[0].timestamp
        if time_range > 3600:
            zoom_start = round((1 - 3600 / time_range) * 100, 2)

    line = (
        Line(init_opts=opts.InitOpts(chart_id=chart_id))
        .add_xaxis(times)
        .add_yaxis(
            _CHART_NAMES["speed_in"],
            data_in,
            yaxis_index=0,
            color=_CHART_COLORS["speed_in"],
            is_smooth=False,
            is_symbol_show=False,
            label_opts=opts.LabelOpts(is_show=False),
            sampling="lttb",
        )
        .add_yaxis(
            _CHART_NAMES["speed_out"],
            data_out,
            yaxis_index=0,
            color=_CHART_COLORS["speed_out"],
            is_smooth=False,
            is_symbol_show=False,
            label_opts=opts.LabelOpts(is_show=False),
            sampling="lttb",
        )
        .add_yaxis(
            _CHART_NAMES["current_conns"],
            data_conns,
            yaxis_index=1,
            color=_CHART_COLORS["current_conns"],
            is_smooth=False,
            is_symbol_show=False,
            label_opts=opts.LabelOpts(is_show=False),
            sampling="lttb",
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(
                title=title,
                pos_left="center",
                title_textstyle_opts=opts.TextStyleOpts(
                    font_size=14, font_weight="normal"
                ),
            ),
            legend_opts=opts.LegendOpts(pos_top="top", pos_left="left"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            xaxis_opts=opts.AxisOpts(
                boundary_gap=False,
                axislabel_opts=opts.LabelOpts(rotate=45, font_size=9),
            ),
            datazoom_opts=[
                opts.DataZoomOpts(
                    range_start=zoom_start,
                    range_end=100,
                    height=10,
                ),
            ],
        )
    )

    line.options["grid"] = opts.GridOpts(
        pos_left="3%", pos_right="4%",
        pos_bottom="18%", is_contain_label=True,
    ).opts

    bandwidth_fmt = JsCode(
        "function(v){"
        "if(v>=1000000)return(v/1000000).toFixed(1)+'MB/s';"
        "if(v>=1000)return(v/1000).toFixed(1)+'KB/s';"
        "return v.toFixed(0)+'B/s';"
        "}"
    )
    line.options["yAxis"] = [
        opts.AxisOpts(
            type_="value", name="\u5e26\u5bbd",
            axislabel_opts=opts.LabelOpts(formatter=bandwidth_fmt),
        ).opts,
        opts.AxisOpts(
            type_="value", name="\u8fde\u63a5\u6570",
        ).opts,
    ]

    options = line.dump_options()
    _chart_opts_queue.append((chart_id, options))
    return (
        f'<div id="{chart_id}" style="width:100%;height:{height}px;"></div>'
    )


def _make_chart_js() -> str:
    if not _chart_opts_queue:
        return ""
    parts = []
    for cid, opts in _chart_opts_queue:
        parts.append(
            f'var el=document.getElementById("{cid}");'
            f'if(el&&!echarts.getInstanceByDom(el))'
            f'{{echarts.init(el).setOption({opts},true);}}'
        )
    _chart_opts_queue.clear()
    js = ''.join(parts)
    return (
        '(function(){'
        'function _i(){'
        'if(window.echarts){' + js + '}'
        'else setTimeout(_i,200)}'
        '_i()'
        '})()'
    )


def _render_charts() -> None:
    with use_scope("charts", clear=True):
        total_pts = _history.get("__total__", [])
        if len(total_pts) >= 2:
            put_html(_build_echarts_html("chart_total", total_pts, "\u603b\u6d41\u91cf\u8d8b\u52bf (24h)", height=500))


def _render_add_form() -> None:
    with use_scope("add_form", clear=True):
        put_collapse("Add Port Mapping", [
            put_row([
                put_column([
                    put_input("ext_port", label="External Port", type=NUMBER,
                              placeholder="e.g. 8080"),
                    put_select("proto", label="Protocol", options=[("TCP", "tcp"), ("UDP", "udp")],
                               value="tcp"),
                ]).style("flex:1"),
                put_column([
                    put_input("int_client", label="Internal Client IP",
                              placeholder="e.g. 192.168.1.100"),
                    put_input("int_port", label="Internal Port", type=NUMBER,
                              placeholder="e.g. 9090"),
                ]).style("flex:1"),
                put_column([
                    put_input("desc", label="Description (optional)",
                              placeholder="e.g. Web Server"),
                    put_input("lease", label="Lease Duration",
                              type=NUMBER, value=0,
                              placeholder="0 = unlimited, e.g. 86400 (1 day)"),
                ]).style("flex:1"),
                put_column([
                    put_text(""),
                    put_button("Add", color="success", onclick=_handle_add),
                ]).style("flex:0 0 auto;justify-content:flex-end"),
            ]).style("gap:12px;align-items:flex-start"),
        ], open=False)


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
        client.add_port_mapping(
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


def _put_hidden_chart(container_id: str, key: str) -> None:
    pts = _history.get(key, [])
    if len(pts) < 2:
        return
    chart_id = "chart_" + key.replace("/", "_")
    put_html(
        f'<div id="{container_id}" '
        f'style="visibility:hidden;position:absolute;top:0;left:0;width:100%;height:300px">'
        f'{_build_echarts_html(chart_id, pts, key, height=300)}'
        f'</div>'
    )


def _render_table(mappings: List[Dict], stats: Dict) -> None:
    with use_scope("table_area", clear=True):
        if not mappings:
            put_info("No port mappings found")
            return

        avail = stats.get("available", False)

        header = [
            span("\u25a2", row=2),
            span("\u25b6", row=2),
            span("#", row=2),
            span("Description / Name", row=2),
            span("Port", row=2),
            span("Proto", row=2),
            span("Internal", row=2),
            span("Int. Port", row=2),
            span("State", row=2),
            span("Conns", row=2),
            span("Traffic", col=2),
            span("Speed", col=2),
            span("Lease", row=2),
            span("Action", row=2),
        ]
        rows = [["In", "Out", "In", "Out"]]

        for idx, m in enumerate(mappings, 1):
            state_label = "ON" if m.get("enabled") else "OFF"
            state_color = "success" if m.get("enabled") else "secondary"
            conns = str(m.get("current_conns", 0)) if m.get("has_stats") else "-"
            lease = _fmt_duration(m.get("lease_remaining", 0))

            ext_port = m.get("external_port", 0)
            proto_lower = m.get("protocol", "TCP").lower()

            if m.get("has_stats"):
                traffic_in = _fmt_bytes(m.get("input_bytes", 0)) if avail else "-"
                traffic_out = _fmt_bytes(m.get("output_bytes", 0)) if avail else "-"
                speed_in = _fmt_speed(m.get("speed_in", 0)) or "-"
                speed_out = _fmt_speed(m.get("speed_out", 0)) or "-"
            else:
                traffic_in = "-"
                traffic_out = "-"
                speed_in = "-"
                speed_out = "-"

            cb_name = f"sel_{ext_port}_{proto_lower}"
            rows.append([
                put_checkbox(cb_name, options=[("", "selected")], inline=True),
                put_html(f'<span class="expand-trigger" data-idx="{idx-1}" style="cursor:pointer;user-select:none">\u25b6</span>'),
                idx,
                m.get("display_name", m.get("name", "")),
                str(m.get("external_port", "")),
                m.get("protocol", "TCP"),
                m.get("internal_client", ""),
                str(m.get("internal_port", "")),
                put_text(state_label).style(f"color:var(--bs-{state_color});font-weight:600"),
                conns,
                traffic_in,
                traffic_out,
                speed_in,
                speed_out,
                lease,
                put_button("Delete", color="danger", small=True,
                           onclick=lambda p=ext_port, q=proto_lower: _confirm_delete(p, q)),
            ])

        total_conns = str(stats.get("total_current_conns", 0))
        total_input = stats.get("total_input_bytes", 0)
        total_output = stats.get("total_output_bytes", 0)
        total_speed_in = sum(float(m.get("speed_in", 0)) for m in mappings)
        total_speed_out = sum(float(m.get("speed_out", 0)) for m in mappings)
        if avail:
            foot_ti = _fmt_bytes(total_input)
            foot_to = _fmt_bytes(total_output)
            foot_si = _fmt_speed(total_speed_in) or "-"
            foot_so = _fmt_speed(total_speed_out) or "-"
        else:
            foot_ti = "-"
            foot_to = "-"
            foot_si = "-"
            foot_so = "-"
        rows.append([
            put_checkbox("sel_all", options=[("", "selected")], inline=True),
            span("", col=8),
            total_conns,
            foot_ti,
            foot_to,
            foot_si,
            foot_so,
            "",
            put_button("Delete", color="danger", small=True, onclick=_delete_selected),
        ])

        put_table(rows, header=header)

        for idx, m in enumerate(mappings):
            ext_port = m.get("external_port", 0)
            proto_lower = m.get("protocol", "TCP").lower()
            chart_id = "chart_source_" + str(idx)
            _put_hidden_chart(chart_id, f"{proto_lower}/{ext_port}")

        put_html("""<script>
(function() {
  var tableArea = document.querySelector('#pywebio-scope-table_area');
  var table = tableArea ? tableArea.querySelector('table') : null;
  if (!table) return;

  var tbody = table.querySelector('tbody');
  if (tbody) {
    var rows = tbody.querySelectorAll('tr');
    if (rows.length) {
      rows[1].classList.add('sub-header');
      rows[rows.length - 1].classList.add('footer-row');
    }
  }

  function toggleDeleteBtn() {
    var cbs = document.querySelectorAll('input[type="checkbox"]');
    var checked = false;
    for (var i = 0; i < cbs.length; i++) {
      if (cbs[i].name && cbs[i].name.startsWith('sel_') && cbs[i].checked) { checked = true; break; }
    }
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.trim() === 'Delete' && !btns[i].classList.contains('btn-sm')) {
        btns[i].disabled = !checked;
      }
    }
  }
  document.addEventListener('change', toggleDeleteBtn);
  setTimeout(toggleDeleteBtn, 500);

  var selAll = document.querySelector('input[name="sel_all"]');
  if (selAll) {
    selAll.addEventListener('change', function() {
      var checked = this.checked;
      var allCbs = document.querySelectorAll('input[type="checkbox"]');
      var evt = new Event('change', { bubbles: true });
      for (var i = 0; i < allCbs.length; i++) {
        if (allCbs[i].name && allCbs[i].name.startsWith('sel_')) {
          allCbs[i].checked = checked;
          allCbs[i].dispatchEvent(evt);
        }
      }
    });
  }

  var savedScroll = 0;
  setInterval(function() {
    var area = document.querySelector('#pywebio-scope-table_area');
    if (area) savedScroll = area.scrollTop;
  }, 500);

  function moveChartToDetail(idx, detail) {
    var src = document.getElementById('chart_source_' + idx);
    if (!src || !src.children.length) return;
    var content = detail.querySelector('.detail-content');
    if (!content) return;
    content.innerHTML = '';
    Array.from(src.children).forEach(function(el) { content.appendChild(el); });
    var chartDiv = content.querySelector('[id^="chart_"]');
    if (chartDiv) {
      var c = echarts.getInstanceByDom(chartDiv);
      if (c) setTimeout(function() { c.resize(); }, 50);
    }
  }

  function _countTableCols() {
    if (!table || !table.rows.length) return 0;
    var cols = 0, row = table.rows[0];
    for (var i = 0; i < row.cells.length; i++) {
      cols += row.cells[i].colSpan || 1;
    }
    return cols;
  }

  function _applyZebra() {
    if (!table) return;
    var dataIdx = 0;
    for (var i = 0; i < table.rows.length; i++) {
      var row = table.rows[i];
      if (row.classList.contains('sub-header') ||
          row.classList.contains('footer-row') ||
          row.classList.contains('detail-row')) continue;
      var isEven = (dataIdx % 2 === 0);
      for (var j = 0; j < row.cells.length; j++) {
        var cell = row.cells[j];
        if (cell.tagName !== 'TD') continue;
        if (isEven) {
          cell.style.backgroundColor = '#edf2f7';
          cell.dataset.zebra = '1';
        } else if (!cell.dataset.zebra) {
          cell.style.backgroundColor = '';
        }
      }
      dataIdx++;
    }
    // Also clear inline bg on non-data rows to avoid conflicts
    document.querySelectorAll('.detail-row td, .sub-header td, .footer-row td').forEach(function(td) {
      td.style.backgroundColor = '';
    });
  }

  function insertDetailRows() {
    if (!table || table.rows.length < 2) return;
    var nCols = _countTableCols();
    var dataIdx = 0;
    for (var i = 2; i < table.rows.length - 1; i++) {
      var detail = document.createElement('tr');
      detail.id = 'detail-row-' + dataIdx;
      detail.className = 'detail-row';
      detail.style.display = 'none';
      var td = document.createElement('td');
      td.colSpan = nCols;
      td.style.padding = '0';
      td.innerHTML = '<div class="detail-content" style="width:100%;box-sizing:border-box"></div>';
      detail.appendChild(td);
      table.rows[i].parentNode.insertBefore(detail, table.rows[i].nextSibling);
      dataIdx++;
      i++;
    }
    document.querySelectorAll('.expand-trigger').forEach(function(el) {
      el.addEventListener('click', function(e) {
        e.stopPropagation();
        var idx = this.getAttribute('data-idx');
        var detail = document.getElementById('detail-row-' + idx);
        if (!detail) return;
        var hidden = detail.style.display === 'none' || !detail.style.display;
        if (hidden) {
          detail.style.display = 'table-row';
          moveChartToDetail(idx, detail);
        } else {
          detail.style.display = 'none';
        }
      });
    });
    // Re-apply zebra after detail rows are inserted
    _applyZebra();
    var area = document.querySelector('#pywebio-scope-table_area');
    if (area && savedScroll > 0) { area.scrollTop = savedScroll; }
  }
  setTimeout(insertDetailRows, 500);
})();
</script>""")


def _confirm_delete(ext_port: int, proto: str) -> None:
    label = f"{proto}/{ext_port}"
    with popup(f"Delete {label}?"):
        put_text(f"Are you sure you want to delete port mapping {label}?")
        put_buttons([
            dict(label="Delete", value="delete", color="danger"),
            dict(label="Cancel", value="cancel"),
        ], onclick=lambda v: _do_delete(v, ext_port, proto))


def _do_delete(action: str, ext_port: int, proto: str) -> None:
    if action != "delete":
        close_popup()
        return
    try:
        client.delete_port_mapping(ext_port, proto)
        toast(f"Deleted: {proto}/{ext_port}", color="info")
        close_popup()
        _refresh()
    except (GostConnectionError, GostApiError) as exc:
        toast(f"Delete failed: {exc}", color="error")
        logger.warning("Delete failed: %s", exc)
        close_popup()


def _delete_selected() -> None:
    try:
        mappings = client.get_port_mappings()
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
    success, failed = client.delete_port_mappings_batch(port_proto_list)
    close_popup()
    msg = f"Deleted: {success}"
    if failed:
        msg += f", Failed: {failed}"
    toast(msg, color="success" if not failed else "warn")
    _refresh()


_selected_cache: Dict[str, Any] = {}
_prev_count = 0


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
    run_js(f"""
    (function() {{
        var data = {data_json};
        data.forEach(function(r) {{
            var cb = document.querySelector('input[name="' + r.cb + '"]');
            if (!cb) return;
            var tr = cb.closest('tr');
            if (!tr || !tr.cells || tr.cells.length < 16) return;
            var c = tr.cells;
            c[8].innerHTML = '<span style="color:var(--bs-' + r.sc + ');font-weight:600">' + r.state + '</span>';
            c[9].textContent = r.conns;
            c[10].textContent = r.ti;
            c[11].textContent = r.to;
            c[12].textContent = r.si;
            c[13].textContent = r.so;
            c[14].textContent = r.lease;
        }});
        var footer = {footer_json};
        var ftr = document.querySelector('.footer-row');
        if (ftr) {{
            var fc = ftr.cells;
            if (fc.length >= 7) {{
                fc[2].textContent = footer.conns;
                fc[3].textContent = footer.ti;
                fc[4].textContent = footer.to;
                fc[5].textContent = footer.si;
                fc[6].textContent = footer.so;
            }}
        }}
    }})();
    """)


def _refresh() -> None:
    if not _REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        mappings = client.get_port_mappings()
        stats = client.get_summary_stats()

        global _prev_count
        count_changed = len(mappings) != _prev_count
        _prev_count = len(mappings)

        _render_summary(mappings, stats)

        _record_data_points(mappings, stats)
        _render_charts()

        if not mappings:
            _render_table(mappings, stats)
        elif count_changed:
            _selected_cache.clear()
            for m in mappings:
                ext_port = m.get("external_port")
                proto = m.get("protocol", "TCP").lower()
                cb_name = f"sel_{ext_port}_{proto}"
                try:
                    if pin.get(cb_name, []):
                        _selected_cache[cb_name] = True
                except Exception:
                    pass

            _render_table(mappings, stats)

            for cb_name in _selected_cache:
                try:
                    pin_update(cb_name, value=["selected"])
                except Exception:
                    pass
        else:
            _update_table_data(mappings, stats)

        run_js(_make_chart_js())
    except SessionNotFoundException:
        logger.debug("Session closed - stopping refresh")
        raise
    except (GostConnectionError, GostApiError):
        logger.debug("Refresh skipped - GOST API unreachable")
    except Exception:
        logger.exception("Refresh failed")
    finally:
        _chart_opts_queue.clear()
        _REFRESH_LOCK.release()


_CUSTOM_CSS = """
            #output-container{width:fit-content;max-width:100%;min-height:98svh;
                              display:flex;flex-direction:column;margin:0 auto;
                              box-sizing:border-box}
            #markdown-body{display:flex;flex-direction:column;flex:1;min-height:0}
            #pywebio-scope-ROOT{display:flex;flex-direction:column;flex:1;min-height:0}
            #pywebio-scope-table_area{flex:1;min-height:0}
            #pywebio-scope-add_form{flex-shrink:0}
            #pywebio-scope-charts{flex-shrink:0}
              table td, table th{text-align:center}
              .detail-content{min-height:300px;width:100%;box-sizing:border-box;background:#f8f9fa;border:1px dashed #dee2e6;border-radius:0}
              .markdown-body tbody tr:first-child th{background:#e9ecef}
              .markdown-body tbody tr.sub-header td{background:#e9ecef;font-weight:600}
              .markdown-body tbody tr.footer-row td{font-weight:600;border-top:2px solid #dee2e6;background:#fafafa}
            """

def main() -> None:
    config(title="GOST Port Mapping Web UI", theme="yeti",
           css_style=_CUSTOM_CSS)

    run_js(_ECHARTS_CDN_JS)

    try:
        mappings = client.get_port_mappings()
        stats = client.get_summary_stats()
    except (GostConnectionError, GostApiError):
        mappings = []
        stats = {}
        put_warning(
            "Cannot connect to GOST API - "
            "check that GOST is running and reachable."
        )

    global _prev_count
    _prev_count = len(mappings)

    put_scope("summary")
    put_scope("charts")
    put_scope("table_area")
    put_scope("add_form")

    _render_summary(mappings, stats)
    if mappings:
        _record_data_points(mappings, stats)
    _render_charts()
    _render_table(mappings, stats)
    run_js(_make_chart_js())
    _render_add_form()

    _stop_refresh = threading.Event()

    def _refresh_worker():
        while not _stop_refresh.wait(Config.GOST_WEBUI_REFRESH_INTERVAL):
            try:
                _refresh()
            except SessionNotFoundException:
                logger.debug("Refresh worker exiting - session closed")
                break

    t = threading.Thread(target=_refresh_worker, daemon=True)
    register_thread(t)
    t.start()
    defer_call(lambda: _stop_refresh.set())

import logging
from typing import Any, Dict, List, Optional

from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.commons.utils import JsCode
from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *

from gost_client import GostApiError, GostConnectionError
from webui_format import (
    _CHART_COLORS, _CHART_NAMES, _COLORS,
    _downsample, _fmt_bytes, _fmt_duration, _fmt_speed, _fmt_time,
    _prepare_summary_data,
    ChartState, DataPoint,
)

logger = logging.getLogger("alter_upnpd.gost_webui.render")


_ECHARTS_CDN_JS = (
    "require.config({paths:{'echarts':'/static/js/echarts.min'}});"
    "require(['echarts'],function(e){window.echarts=e;})"
)


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
        put_row([
            _card(label, value, color)
            for label, value, color in _prepare_summary_data(mappings, stats)
        ]).style("gap:16px;margin-bottom:16px")


def _build_echarts_html(
    cs: ChartState,
    chart_id: str,
    points: List[DataPoint],
    title: str = "",
    height: int = 220,
) -> str:
    if not points or len(points) < 2:
        return ""

    pts = _downsample(points, max_points=cs.display_max)
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
    cs.chart_opts_queue.append((chart_id, options))
    return (
        f'<div id="{chart_id}" style="width:100%;height:{height}px;"></div>'
    )


def _render_charts(cs: ChartState) -> None:
    with use_scope("charts", clear=True):
        total_pts = cs.history.get("__total__", [])
        if len(total_pts) >= 2:
            put_html(_build_echarts_html(cs, "chart_total", total_pts, "\u603b\u6d41\u91cf\u8d8b\u52bf (24h)", height=500))


def _render_add_form(on_add) -> None:
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
                    put_button("Add", color="success", onclick=on_add),
                ]).style("flex:0 0 auto;justify-content:flex-end"),
            ]).style("gap:12px;align-items:flex-start"),
        ], open=False)


def _put_hidden_chart(cs: ChartState, container_id: str, key: str) -> None:
    pts = cs.history.get(key, [])
    if len(pts) < 2:
        return
    chart_id = "chart_" + key.replace("/", "_")
    put_html(
        f'<div id="{container_id}" '
        f'style="visibility:hidden;position:absolute;top:0;left:0;width:100%;height:300px">'
        f'{_build_echarts_html(cs, chart_id, pts, key, height=300)}'
        f'</div>'
    )


def _prepare_table_header() -> List[Any]:
    return [
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


def _build_data_row(mapping: Dict, idx: int, avail: bool, on_delete) -> List[Any]:
    state_label = "ON" if mapping.get("enabled") else "OFF"
    state_color = "success" if mapping.get("enabled") else "secondary"
    conns = str(mapping.get("current_conns", 0)) if mapping.get("has_stats") else "-"
    lease = _fmt_duration(mapping.get("lease_remaining", 0))

    ext_port = mapping.get("external_port", 0)
    proto_lower = mapping.get("protocol", "TCP").lower()

    if mapping.get("has_stats"):
        traffic_in = _fmt_bytes(mapping.get("input_bytes", 0)) if avail else "-"
        traffic_out = _fmt_bytes(mapping.get("output_bytes", 0)) if avail else "-"
        speed_in = _fmt_speed(mapping.get("speed_in", 0)) or "-"
        speed_out = _fmt_speed(mapping.get("speed_out", 0)) or "-"
    else:
        traffic_in = "-"
        traffic_out = "-"
        speed_in = "-"
        speed_out = "-"

    cb_name = f"sel_{ext_port}_{proto_lower}"
    return [
        put_checkbox(cb_name, options=[("", "selected")], inline=True),
        put_html(f'<span class="expand-trigger" data-idx="{idx - 1}" style="cursor:pointer;user-select:none">\u25b6</span>'),
        idx + 1,
        mapping.get("display_name", mapping.get("name", "")),
        str(mapping.get("external_port", "")),
        mapping.get("protocol", "TCP"),
        mapping.get("internal_client", ""),
        str(mapping.get("internal_port", "")),
        put_text(state_label).style(f"color:var(--bs-{state_color});font-weight:600"),
        conns,
        traffic_in,
        traffic_out,
        speed_in,
        speed_out,
        lease,
        put_button("Delete", color="danger", small=True,
                   onclick=lambda p=ext_port, q=proto_lower: on_delete(p, q)),
    ]


def _build_footer_row(stats: Dict, mappings: List[Dict], avail: bool, on_delete_selected) -> List[Any]:
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
    return [
        put_checkbox("sel_all", options=[("", "selected")], inline=True),
        span("", col=8),
        total_conns,
        foot_ti,
        foot_to,
        foot_si,
        foot_so,
        "",
        put_button("Delete", color="danger", small=True, onclick=on_delete_selected),
    ]


_TABLE_INIT_SCRIPT = """<script>
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
    tableArea.addEventListener('click', function(e) {
      var trigger = e.target.closest('.expand-trigger');
      if (!trigger) return;
      var idx = trigger.getAttribute('data-idx');
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
    _applyZebra();
    var area = document.querySelector('#pywebio-scope-table_area');
    if (area && savedScroll > 0) { area.scrollTop = savedScroll; }
  }
  setTimeout(insertDetailRows, 500);
})();
</script>"""


def _render_table(
    cs: ChartState,
    mappings: List[Dict],
    stats: Dict,
    on_delete,
    on_delete_selected,
) -> None:
    with use_scope("table_area", clear=True):
        if not mappings:
            put_info("No port mappings found")
            return

        avail = stats.get("available", False)

        header = _prepare_table_header()
        rows: List[Any] = [["In", "Out", "In", "Out"]]

        for idx, m in enumerate(mappings):
            rows.append(_build_data_row(m, idx, avail, on_delete))

        rows.append(_build_footer_row(stats, mappings, avail, on_delete_selected))

        put_table(rows, header=header)

        for idx, m in enumerate(mappings):
            ext_port = m.get("external_port", 0)
            proto_lower = m.get("protocol", "TCP").lower()
            chart_id = "chart_source_" + str(idx)
            _put_hidden_chart(cs, chart_id, f"{proto_lower}/{ext_port}")

        put_html(_TABLE_INIT_SCRIPT)


def _confirm_delete(ext_port: int, proto: str, on_delete) -> None:
    label = f"{proto}/{ext_port}"
    with popup(f"Delete {label}?"):
        put_text(f"Are you sure you want to delete port mapping {label}?")
        put_buttons([
            dict(label="Delete", value="delete", color="danger"),
            dict(label="Cancel", value="cancel"),
        ], onclick=lambda v: on_delete(v, ext_port, proto))


def _build_table_update_js(data_json: str, footer_json: str) -> str:
    return f"""
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
    """


def _make_chart_js(cs: ChartState) -> str:
    queue = cs.chart_opts_queue
    if not queue:
        return ""
    parts = []
    for cid, opts in queue:
        parts.append(
            f'var el=document.getElementById("{cid}");'
            f'if(el&&!echarts.getInstanceByDom(el))'
            f'{{echarts.init(el).setOption({opts},true);}}'
        )
    queue.clear()
    js = ''.join(parts)
    return (
        '(function(){'
        'function _i(){'
        'if(window.echarts){' + js + '}'
        'else setTimeout(_i,200)}'
        '_i()'
        '})()'
    )


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

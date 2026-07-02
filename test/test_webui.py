import time as time_module
import pytest
from unittest.mock import patch

from webui_format import (
    _fmt_bytes, _fmt_speed, _fmt_duration, _fmt_time,
    _downsample, _record_data_points,
    DataPoint,
)
from webui_render import _make_chart_js
from webui import _state


@pytest.fixture(autouse=True)
def _reset_webui_globals():
    cs = _state.chart
    cs.history.clear()
    cs.chart_opts_queue.clear()
    cs.prev_total_input = 0
    cs.prev_total_output = 0
    cs.prev_total_time = 0.0
    yield
    cs.history.clear()
    cs.chart_opts_queue.clear()
    cs.prev_total_input = 0
    cs.prev_total_output = 0
    cs.prev_total_time = 0.0


# ── _fmt_bytes ──


class TestFmtBytes:
    def test_zero(self):
        assert _fmt_bytes(0) == "0B"

    def test_bytes_under_1024(self):
        assert _fmt_bytes(1) == "1B"
        assert _fmt_bytes(1023) == "1023B"

    def test_kb(self):
        assert _fmt_bytes(1024) == "1.0KB"
        assert _fmt_bytes(1536) == "1.5KB"

    def test_mb(self):
        assert _fmt_bytes(1048576) == "1.0MB"
        assert _fmt_bytes(1572864) == "1.5MB"

    def test_gb(self):
        assert _fmt_bytes(1073741824) == "1.0GB"

    def test_tb(self):
        assert _fmt_bytes(1099511627776) == "1.0TB"

    def test_pb(self):
        assert _fmt_bytes(1125899906842624) == "1.0PB"

    def test_negative(self):
        assert _fmt_bytes(-1024) == "-1.0KB"

    def test_large_int(self):
        _fmt_bytes(2**63 - 1)


# ── _fmt_speed ──


class TestFmtSpeed:
    def test_zero(self):
        assert _fmt_speed(0) == ""

    def test_negative(self):
        assert _fmt_speed(-1) == ""

    def test_bytes_per_sec(self):
        assert _fmt_speed(500) == "500B/s"
        assert _fmt_speed(1023) == "1023B/s"

    def test_kb_per_sec(self):
        assert _fmt_speed(1024) == "1.0KB/s"

    def test_mb_per_sec(self):
        assert _fmt_speed(1048576) == "1.0MB/s"

    def test_gb_per_sec(self):
        assert _fmt_speed(1073741824) == "1.0GB/s"

    def test_pb_fallback(self):
        assert "PB/s" in _fmt_speed(1125899906842624)

    def test_float_input(self):
        assert _fmt_speed(1024.5) == "1.0KB/s"


# ── _fmt_duration ──


class TestFmtDuration:
    def test_zero(self):
        assert _fmt_duration(0) == "-"

    def test_negative(self):
        assert _fmt_duration(-1) == "-"

    def test_seconds(self):
        assert _fmt_duration(1) == "1s"
        assert _fmt_duration(59) == "59s"

    def test_minutes_and_seconds(self):
        assert _fmt_duration(60) == "1m"
        assert _fmt_duration(125) == "2m 5s"

    def test_hours(self):
        assert _fmt_duration(3600) == "1h"
        assert _fmt_duration(3665) == "1h 1m 5s"

    def test_days(self):
        assert _fmt_duration(86400) == "1d"
        assert _fmt_duration(90061) == "1d 1h 1m 1s"

    def test_large(self):
        assert "d" in _fmt_duration(86400 * 365)


# ── _fmt_time ──


class TestFmtTime:
    def test_format_hh_mm_ss(self):
        assert len(_fmt_time(946684800)) == 8
        assert _fmt_time(946684800).count(":") == 2

    def test_components_two_digit(self):
        h, m, s = _fmt_time(946684800).split(":")
        assert len(h) == 2 and len(m) == 2 and len(s) == 2

    def test_ranges(self):
        import random
        for _ in range(20):
            ts = random.randint(0, 2_000_000_000)
            h, m, s = _fmt_time(ts).split(":")
            assert 0 <= int(h) <= 23
            assert 0 <= int(m) <= 59
            assert 0 <= int(s) <= 59

    def test_localtime(self):
        with patch("webui_format.time") as mock_time:
            mock_time.localtime.return_value = time_module.struct_time(
                (2025, 6, 26, 14, 30, 45, 3, 177, 0)
            )
            assert _fmt_time(0) == "14:30:45"


# ── DataPoint ──


class TestDataPoint:
    def test_fields(self):
        dp = DataPoint(1000.0, 10.5, 20.3, 5)
        assert dp.timestamp == 1000.0
        assert dp.speed_in == 10.5
        assert dp.speed_out == 20.3
        assert dp.current_conns == 5

    def test_types(self):
        dp = DataPoint(1.0, 2.0, 3.0, 4)
        assert isinstance(dp.timestamp, float)
        assert isinstance(dp.current_conns, int)


# ── _downsample ──


class TestDownsample:
    def test_empty(self):
        assert _downsample([], max_points=10) == []

    def test_single(self):
        pts = [DataPoint(1.0, 0.0, 0.0, 0)]
        assert _downsample(pts, max_points=10) == pts

    def test_under_limit(self):
        pts = [DataPoint(float(i), 1.0, 1.0, 1) for i in range(5)]
        assert _downsample(pts, max_points=10) == pts

    def test_at_limit(self):
        pts = [DataPoint(float(i), 1.0, 1.0, 1) for i in range(10)]
        assert _downsample(pts, max_points=10) == pts

    def test_over_limit_first_point(self):
        pts = [DataPoint(float(i), float(i), float(i * 2), i) for i in range(100)]
        result = _downsample(pts, max_points=10)
        assert len(result) == 10
        assert result[0] == pts[0]
        assert result[-1] == pts[90]

    def test_over_limit_preserves_order(self):
        pts = [DataPoint(float(i), float(i), float(i * 2), i) for i in range(100)]
        result = _downsample(pts, max_points=10)
        for i in range(1, len(result)):
            assert result[i].timestamp > result[i - 1].timestamp

    def test_large_dataset(self):
        pts = [DataPoint(float(i), 0.0, 0.0, 0) for i in range(10000)]
        result = _downsample(pts, max_points=50)
        assert len(result) == 50

    def test_preserves_values(self):
        pts = [DataPoint(float(i), float(i) * 10, float(i) * 20, i) for i in range(100)]
        result = _downsample(pts, max_points=10)
        for dp in result:
            assert dp.speed_in == dp.timestamp * 10
            assert dp.speed_out == dp.timestamp * 20
            assert dp.current_conns == int(dp.timestamp)

    def test_uses_module_default(self):
        pts = [DataPoint(float(i), 1.0, 1.0, 1) for i in range(_state.chart.display_max)]
        result = _downsample(pts, max_points=_state.chart.display_max)
        assert len(result) == _state.chart.display_max


# ── _record_data_points ──


def _mapping(port=8080, protocol="TCP", si=0, so=0, conns=0):
    return {
        "protocol": protocol, "external_port": port,
        "speed_in": si, "speed_out": so, "current_conns": conns,
    }


def _stats(t_in=0, t_out=0, conns=0):
    return {
        "total_input_bytes": t_in, "total_output_bytes": t_out,
        "total_current_conns": conns,
    }


class TestRecordDataPoints:
    def test_creates_per_port_history(self):
        _record_data_points(_state.chart, [_mapping(8080)], _stats())
        assert "tcp/8080" in _state.chart.history
        assert len(_state.chart.history["tcp/8080"]) == 1

    def test_creates_total_key(self):
        _record_data_points(_state.chart, [_mapping(8080)], _stats())
        assert "__total__" in _state.chart.history

    def test_first_call_speed_zero(self):
        _record_data_points(_state.chart, [_mapping(8080)], _stats(t_in=1000, t_out=2000))
        assert _state.chart.history["__total__"][0].speed_in == 0.0
        assert _state.chart.history["__total__"][0].speed_out == 0.0

    def test_second_call_computes_speed(self):
        with patch("webui_format.time") as t:
            t.time.side_effect = [1000.0, 1010.0]
            _record_data_points(_state.chart, [_mapping(8080)], _stats(t_in=1000, t_out=2000, conns=5))
            _record_data_points(_state.chart, [_mapping(8080)], _stats(t_in=3000, t_out=5000, conns=10))

        dp = _state.chart.history["__total__"][1]
        assert abs(dp.speed_in - 200.0) < 0.01
        assert abs(dp.speed_out - 300.0) < 0.01
        assert dp.current_conns == 10

    def test_zero_elapsed_no_crash(self):
        _state.chart.prev_total_input = 1000
        _state.chart.prev_total_output = 2000
        _state.chart.prev_total_time = 1000.0
        with patch("webui_format.time") as t:
            t.time.return_value = 1000.0
            _record_data_points(_state.chart, [_mapping(8080)], _stats(t_in=2000, t_out=4000))

        assert _state.chart.history["__total__"][0].speed_in == 0.0

    def test_multiple_mappings(self):
        mappings = [_mapping(8080, "TCP"), _mapping(9090, "UDP")]
        _record_data_points(_state.chart, mappings, _stats())
        assert "tcp/8080" in _state.chart.history
        assert "udp/9090" in _state.chart.history
        assert len(_state.chart.history) == 3

    def test_per_port_metrics(self):
        _record_data_points(_state.chart, [_mapping(8080, si=100, so=200, conns=3)], _stats())
        dp = _state.chart.history["tcp/8080"][0]
        assert dp.speed_in == 100
        assert dp.speed_out == 200
        assert dp.current_conns == 3

    def test_history_capped(self):
        saved = _state.chart.max_history
        _state.chart.max_history = 3
        try:
            for _ in range(5):
                _record_data_points(_state.chart, [_mapping(8080)], _stats())
            assert len(_state.chart.history["tcp/8080"]) == 3
            assert len(_state.chart.history["__total__"]) == 3
        finally:
            _state.chart.max_history = saved

    def test_append_multiple_calls(self):
        for _ in range(5):
            _record_data_points(_state.chart, [_mapping(8080)], _stats())
        assert len(_state.chart.history["tcp/8080"]) == 5

    def test_empty_mappings_creates_total(self):
        _record_data_points(_state.chart, [], _stats(conns=7))
        assert _state.chart.history["__total__"][0].current_conns == 7

    def test_updates_prev_totals(self):
        _record_data_points(_state.chart, [_mapping(8080)], _stats(t_in=500, t_out=1000))
        assert _state.chart.prev_total_input == 500
        assert _state.chart.prev_total_output == 1000
        assert _state.chart.prev_total_time > 0


# ── _make_chart_js ──


class TestMakeChartJs:
    def test_empty_queue(self):
        assert _make_chart_js(_state.chart) == ""

    def test_clears_queue(self):
        _state.chart.chart_opts_queue.append(("c1", "{}"))
        _make_chart_js(_state.chart)
        assert _state.chart.chart_opts_queue == []

    def test_retry_wrapper(self):
        _state.chart.chart_opts_queue.append(("c1", "{}"))
        js = _make_chart_js(_state.chart)
        assert js.startswith("(function(){")
        assert "setTimeout(_i,200)" in js
        assert js.endswith("})()")

    def test_echarts_init(self):
        _state.chart.chart_opts_queue.append(("my_chart", '{"xAxis":{}}'))
        js = _make_chart_js(_state.chart)
        assert "echarts.getInstanceByDom" in js
        assert "echarts.init" in js

    def test_multi_chart(self):
        _state.chart.chart_opts_queue.append(("c1", "{}"))
        _state.chart.chart_opts_queue.append(("c2", "{}"))
        js = _make_chart_js(_state.chart)
        assert "c1" in js
        assert "c2" in js

    def test_embeds_option(self):
        opts = '{"series":[{"data":[1,2,3]}]}'
        _state.chart.chart_opts_queue.append(("x", opts))
        assert opts in _make_chart_js(_state.chart)

    def test_empty_opts(self):
        _state.chart.chart_opts_queue.append(("c1", ""))
        assert "c1" in _make_chart_js(_state.chart)


# ── _build_echarts_html (requires pyecharts) ──


class TestBuildEchartsHtml:
    def test_empty_points(self):
        from webui_render import _build_echarts_html
        html = _build_echarts_html(_state.chart, "test", [])
        assert html.startswith('<div id="test"')
        assert "height:220px" in html

    def test_single_point(self):
        from webui_render import _build_echarts_html
        html = _build_echarts_html(_state.chart, "test", [DataPoint(1.0, 0, 0, 0)])
        assert html.startswith('<div id="test"')
        assert "height:220px" in html

    def test_two_points_returns_div(self):
        from webui_render import _build_echarts_html
        pts = [DataPoint(1000.0, 10.0, 20.0, 1), DataPoint(1010.0, 15.0, 25.0, 2)]
        html = _build_echarts_html(_state.chart, "chart_test", pts)
        assert html.startswith('<div id="chart_test"')
        assert "height:220px" in html

    def test_queues_opts(self):
        from webui_render import _build_echarts_html
        pts = [DataPoint(1000.0, 10, 20, 1), DataPoint(1010.0, 15, 25, 2)]
        before = len(_state.chart.chart_opts_queue)
        _build_echarts_html(_state.chart, "chart_q", pts)
        assert len(_state.chart.chart_opts_queue) == before + 1


# ── _CUSTOM_CSS ──


class TestCustomCss:
    def test_is_string(self):
        from webui_render import _CUSTOM_CSS
        assert isinstance(_CUSTOM_CSS, str)

    def test_has_table_rules(self):
        from webui_render import _CUSTOM_CSS
        assert ".markdown-body" in _CUSTOM_CSS

    def test_has_container_rule(self):
        from webui_render import _CUSTOM_CSS
        assert "#output-container" in _CUSTOM_CSS

    def test_not_empty(self):
        from webui_render import _CUSTOM_CSS
        assert len(_CUSTOM_CSS.strip()) > 0


# ── _prepare_summary_data ──


class TestPrepareSummaryData:
    def test_empty_mappings(self):
        from webui_format import _prepare_summary_data
        cards = _prepare_summary_data([], {})
        assert len(cards) == 4
        assert cards[0] == ("PORT MAPPINGS", "0", 1)
        assert cards[2] == ("TOTAL TRAFFIC", "-", 2)
        assert cards[3] == ("ERRORS", "-", 1)

    def test_with_stats(self):
        from webui_format import _prepare_summary_data
        stats = {
            "total_current_conns": 5,
            "total_input_bytes": 2048,
            "total_output_bytes": 4096,
            "total_errors": 0,
            "available": True,
        }
        cards = _prepare_summary_data([{"name": "s1"}], stats)
        assert cards[0] == ("PORT MAPPINGS", "1", 1)
        assert cards[1] == ("ACTIVE CONNECTIONS", "5", 0)
        assert cards[2][0] == "TOTAL TRAFFIC"
        assert "KB" in cards[2][1]
        assert cards[3] == ("ERRORS", "0", 1)

    def test_errors_color_danger(self):
        from webui_format import _prepare_summary_data
        stats = {"total_errors": 10, "available": True}
        cards = _prepare_summary_data([], stats)
        assert cards[3] == ("ERRORS", "10", 3)

    def test_traffic_when_not_available(self):
        from webui_format import _prepare_summary_data
        stats = {"total_input_bytes": 9999, "total_output_bytes": 9999, "available": False}
        cards = _prepare_summary_data([], stats)
        assert cards[2] == ("TOTAL TRAFFIC", "-", 2)

    def test_many_mappings(self):
        from webui_format import _prepare_summary_data
        m = [{"name": f"s{i}"} for i in range(42)]
        cards = _prepare_summary_data(m, {})
        assert cards[0] == ("PORT MAPPINGS", "42", 1)


# ── _prepare_table_header ──


class TestPrepareTableHeader:
    def test_length(self):
        from webui_render import _prepare_table_header
        header = _prepare_table_header()
        assert len(header) == 14

    def test_first_column_checkbox(self):
        from webui_render import _prepare_table_header
        header = _prepare_table_header()
        first = str(header[0])
        assert "checkbox" in first.lower() or "\u25a2" in first or "span" in first.lower()

    def has_proto_label(self):
        from webui_render import _prepare_table_header
        header = _prepare_table_header()
        labels = [str(h) for h in header]
        assert any("Proto" in l for l in labels)

    def has_lease_label(self):
        from webui_render import _prepare_table_header
        header = _prepare_table_header()
        labels = [str(h) for h in header]
        assert any("Lease" in l for l in labels)


# ── get_summary_stats ──


class TestGetSummaryStats:
    def test_returns_defaults_when_no_metrics(self):
        from webui_format import get_summary_stats
        client = _FakeGostClient(fetch_result=None)
        result = get_summary_stats(client)
        assert result["available"] is False
        assert result["total_services"] == 0
        assert result["total_current_conns"] == 0

    def test_parses_metrics(self):
        from webui_format import get_summary_stats
        client = _FakeGostClient(fetch_result=True)
        result = get_summary_stats(client)
        assert result["available"] is True
        assert result["total_services"] == 42
        assert result["total_current_conns"] == 7

    def test_metrics_keys(self):
        from webui_format import get_summary_stats
        client = _FakeGostClient(fetch_result=True)
        result = get_summary_stats(client)
        expected_keys = {
            "total_services", "total_current_conns",
            "total_input_bytes", "total_output_bytes",
            "total_requests", "total_errors", "available",
        }
        assert set(result.keys()) == expected_keys


class _FakeGostClient:
    def __init__(self, fetch_result=None):
        self._fetch_result = fetch_result

    def fetch_metrics(self):
        if self._fetch_result is None:
            return None
        return _fake_prometheus_metrics()


def _fake_prometheus_metrics():
    from gost_client import PrometheusMetrics

    class FakePM:
        def first_gauge(self, name):
            fake = {
                "gost_services": 42,
                "gost_service_requests_in_flight": 7,
            }
            return fake.get(name, 0)

        def sum_gauge(self, name):
            fake = {
                "gost_service_requests_in_flight": 7,
            }
            return fake.get(name, 0)

        def sum_counter(self, name):
            fake = {
                "gost_service_transfer_input_bytes": 5000,
                "gost_service_transfer_output_bytes": 10000,
                "gost_service_requests": 99,
                "gost_service_handler_errors": 2,
            }
            return fake.get(name, 0)

    return FakePM()

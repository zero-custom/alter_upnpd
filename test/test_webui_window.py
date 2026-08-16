import time

from webui_format import (
    ChartState,
    DataPoint,
    _decay_downsample,
    _record_data_points,
    _trim_window,
)


def _make_points(now, ages_seconds):
    return [
        DataPoint(
            timestamp=now - age,
            speed_in=1.0,
            speed_out=1.0,
            current_conns=1,
        )
        for age in ages_seconds
    ]


class TestTrimWindow:
    def test_drops_points_older_than_window(self):
        now = 1_000_000.0
        pts = _make_points(now, [0, 3600, 47 * 3600, 49 * 3600])
        kept = _trim_window(pts, now, 48 * 3600)
        ages = sorted(now - p.timestamp for p in kept)
        assert ages == [0, 3600, 47 * 3600]

    def test_empty_when_all_outside_window(self):
        now = 1_000_000.0
        pts = _make_points(now, [100 * 3600])
        kept = _trim_window(pts, now, 48 * 3600)
        # 至少保留最近一个点，避免空图
        assert len(kept) == 1

    def test_no_window_returns_all(self):
        now = 1_000_000.0
        pts = _make_points(now, [0, 10, 100])
        assert _trim_window(pts, now, 0) == pts


class TestDecayDownsample:
    def test_near_segment_denser_than_far(self):
        now = 1_000_000.0
        # 每段塞满远超配额的点，触发降采样
        ages = []
        for seg_max, seg_min in [(4, 0), (12, 4), (28, 12), (48, 28)]:
            ages.extend(range(seg_min * 3600, seg_max * 3600, 30))
        pts = _make_points(now, ages)
        cs = ChartState(window_seconds=48 * 3600, display_max=1000)
        out = _decay_downsample(pts, now, cs.display_max)

        near = [p for p in out if now - p.timestamp <= 4 * 3600]
        far = [p for p in out if 28 * 3600 <= now - p.timestamp <= 48 * 3600]
        assert len(near) > len(far)
        # 总数不超过 display_max
        assert len(out) <= cs.display_max

    def test_output_sorted_and_monotonic(self):
        now = 1_000_000.0
        ages = list(range(0, 48 * 3600, 30))
        pts = _make_points(now, ages)
        out = _decay_downsample(pts, now, 1000)
        ts = [p.timestamp for p in out]
        assert ts == sorted(ts)

    def test_returns_all_when_under_budget(self):
        now = 1_000_000.0
        pts = _make_points(now, [0, 60, 120])
        out = _decay_downsample(pts, now, 1000)
        assert len(out) == 3


class TestRecordDataPointsWindow:
    def test_old_points_evicted_by_window(self):
        cs = ChartState(
            max_history=10_000,
            window_seconds=48 * 3600,
            display_max=1000,
        )
        now = time.time()
        mappings = [{"protocol": "tcp", "external_port": 8080}]

        # 写入一个 50 小时前的旧点（手动塞入历史）
        cs.history.setdefault("tcp/8080", []).append(
            DataPoint(now - 50 * 3600, 0.0, 0.0, 0)
        )
        cs.history.setdefault("__total__", []).append(
            DataPoint(now - 50 * 3600, 0.0, 0.0, 0)
        )

        stats = {
            "total_input_bytes": 0,
            "total_output_bytes": 0,
            "total_current_conns": 0,
        }
        _record_data_points(cs, mappings, stats)

        for key in ("tcp/8080", "__total__"):
            ages = [now - p.timestamp for p in cs.history[key]]
            assert all(a <= 48 * 3600 for a in ages)

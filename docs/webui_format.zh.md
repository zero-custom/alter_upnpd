# webui_format.py — WebUI 数据格式化与聚合

GOST WebUI 仪表板的数据格式化、指标聚合、降采样和图表状态管理。无 PyWebIO 依赖——纯数据转换。

## 类型

| 类型 | 字段 | 说明 |
|---|---|---|
| `DataPoint` | `timestamp, speed_in, speed_out, current_conns` | 每端口时间序列数据点。 |
| `ChartState` | `history, chart_opts_queue, prev_total_*, max_history` | 图表数据累加器。 |

## 格式化函数

| 函数 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `_fmt_bytes(n)` | `int` | `"1.5MB"` | 人类可读的字节大小。 |
| `_fmt_duration(sec)` | `int` | `"2d 3h 15m 30s"` | 人类可读的持续时间。 |
| `_fmt_time(ts)` | `float` | `"14:30:00"` | 从 Unix 时间戳转 HH:MM:SS。 |
| `_fmt_speed(bps)` | `float` | `"1.5MB/s"` | 人类可读的字节速率。 |
| `_downsample(points, max)` | `List[DataPoint]` | `List[DataPoint]` | LTTB 风格降采样，优化图表性能。 |

## 数据函数

| 函数 | 说明 |
|---|---|
| `_record_data_points(cs, mappings, stats)` | 为每个映射和聚合追加新 `DataPoint` 到 `ChartState.history`。基于差值计算速率。超出 `max_history` 时裁剪。 |
| `get_summary_stats(client)` | 通过 `GostClient.fetch_metrics()` 抓取并聚合 Prometheus 指标。返回总服务数、连接数、出入流量、请求数、错误数。 |
| `get_all_services_stats(client)` | 从 `GostClient.get_services()` 读取 per-service 状态统计（当前连接数、总字节数）。 |
| `_prepare_summary_data(mappings, stats)` | 为卡片渲染准备 4 行摘要数据：映射数、活跃连接数、总流量、错误数。 |

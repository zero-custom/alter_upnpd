# webui_format.py — WebUI Data Formatting & Aggregation

Data formatting, metrics aggregation, downsample, and chart state management for the GOST WebUI dashboard. No PyWebIO dependency — pure data transformation.

## Types

| Type | Fields | Description |
|---|---|---|
| `DataPoint` | `timestamp, speed_in, speed_out, current_conns` | Per-port time-series data point. |
| `ChartState` | `history, chart_opts_queue, prev_total_*, max_history` | Accumulator for chart data. |

## Formatting Functions

| Function | Input | Output | Description |
|---|---|---|---|
| `_fmt_bytes(n)` | `int` | `"1.5MB"` | Human-readable byte size. |
| `_fmt_duration(sec)` | `int` | `"2d 3h 15m 30s"` | Human-readable duration. |
| `_fmt_time(ts)` | `float` | `"14:30:00"` | HH:MM:SS from Unix timestamp. **No longer used in chart rendering** — ECharts time axis handles formatting natively. |
| `_fmt_speed(bps)` | `float` | `"1.5MB/s"` | Human-readable byte rate. |
| `_downsample(points, max)` | `List[DataPoint]` | `List[DataPoint]` | LTTB-style downsample for chart performance. Active with `display_max=1000` vs `max_history=8640`. |

## Data Functions

| Function | Description |
|---|---|
| `_record_data_points(cs, mappings, stats)` | Appends new `DataPoint` per mapping + aggregate to `ChartState.history`. Calculates delta-based speed. Trims to `max_history`. |
| `get_summary_stats(client)` | Fetches and aggregates Prometheus metrics via `GostClient.fetch_metrics()`. Returns total services, connections, input/output bytes, requests, errors. |
| `get_all_services_stats(client)` | Reads per-service status stats (current conns, total bytes) from `GostClient.get_services()`. |
| `_prepare_summary_data(mappings, stats)` | Prepares 4 summary rows for card rendering: mapping count, active connections, total traffic, errors. |

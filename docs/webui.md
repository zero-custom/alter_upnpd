# webui.py — GOST Monitoring Dashboard

PyWebIO + ECharts dashboard embedded in the Flask app (route `/`). Provides real-time port mapping monitoring, CRUD operations, and traffic charts.

## Data Sources

| Source | Description |
|---|---|
| GostClient.get_port_mappings() | Port mapping list (protocol, port, status, real-time speed, connections) |
| GostClient.get_summary_stats() | Aggregated stats (total bandwidth, connections, errors via Prometheus metrics) |

## Layout

| Area | Description |
|---|---|
| Summary | Four summary cards: mappings / active connections / total traffic / errors |
| Chart | Total traffic trend line chart (inbound, outbound, connections), default last 1 hour, drag-to-zoom |
| Table | Port mapping table with expandable detail rows showing per-port charts |
| Add Form | Collapsible add-mapping form (External Port / Protocol / Internal Client / Internal Port / Description / Lease) |

## Key Functions

| Function | Description |
|---|---|
| main() | Entry point: initialise PyWebIO page, render initial state, start background refresh thread |
| _refresh() | Periodic refresh: fetch latest mappings and stats, incremental table update (JS cell patch) or full re-render |
| _record_data_points() | Compute bandwidth from Prometheus counter deltas, store time series in `_history` |
| _build_echarts_html() | Build ECharts line chart HTML via pyecharts, with downsampling and dataZoom |
| _render_table() | Render mapping table, pre-render hidden per-port chart containers, JS moves them on expand |
| _update_table_data() | Update only changed cell values via JS innerHTML patch (no flicker) |
| _handle_add() | Handle add-mapping form submission, validate port range, call GostClient |

## Chart Specs

| Property | Value |
|---|---|
| Engine | pyecharts (ECharts 6.x) |
| Max data points | `EnvConfig.gost_webui_history_points` (default 8640, 10s interval = 24h) |
| Refresh interval | `EnvConfig.gost_webui_refresh_interval` (default 10s) |
| Line style | Straight lines (`is_smooth=False`), no data point markers (`is_symbol_show=False`) |
| Zoom | dataZoom defaulting to last 1 hour |
| Colours | Inbound blue, outbound green, connections orange |
| Chart loading | ECharts loaded from local `/static/echarts.min` (CDN checked once at startup) |

## Refresh Mechanism

- Background thread calls `_refresh()` every 10 seconds
- `_REFRESH_LOCK` prevents concurrent refreshes
- When mapping count unchanged: only patch changed cells (DL/UL speed, connections, traffic)
- When mapping count changes: full re-render with checkbox state restoration
- `SessionNotFoundException` causes clean thread exit (stops after page close)

## Table Expandable Rows

A ▶ trigger on each row expands a detail row showing the port's dedicated traffic chart:
- Charts pre-rendered into hidden containers (`visibility:hidden; position:absolute`)
- JS moves DOM nodes into detail row on first expand
- `echarts.resize()` ensures correct container dimensions

## Table Styling

- **Zebra striping**: JS `_applyZebra()` runs after detail row insertion, applies alternating `background-color: #edf2f7` to even-indexed data rows using an independent `dataIdx` counter (non-data rows excluded)
- **Header rows**: Both main header and sub-header share `background: #e9ecef` with no cell borders
- **Footer row**: `background: #fafafa` with top border
- **Detail rows**: `colSpan = 16` (from `_countTableCols()`, corrects PyWebIO's `cells.length = 14`), inner div `width:100%;box-sizing:border-box`
- **CSS specificity**: Rules prefixed with `.markdown-body` to override Yeti theme defaults

## Batch Delete

Select multiple mappings via checkboxes, click the bottom "Delete" button to batch delete via `GostClient.delete_port_mappings_batch()`.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `GOST_WEBUI_REFRESH_INTERVAL` | `10` | Dashboard refresh interval (seconds) |
| `GOST_WEBUI_HISTORY_POINTS` | `8640` | Max data points stored per port |
| `GOST_API_URL` | `http://127.0.0.1:8000` | GOST API base URL |
| `GOST_METRICS_URL` | `""` | Prometheus metrics URL (auto-discovered if empty) |

# webui_render.py — WebUI HTML/JS Rendering

Renders the GOST WebUI dashboard using PyWebIO components (cards, tables, modals) and ECharts JS for charts. Depends on `webui_format` for data preparation.

## Key Functions

| Function | Description |
|---|---|
| `render_dashboard(client, cs)` | Main dashboard render: summary cards, mapping table, per-port detail modal, aggregate charts. |
| `_render_table(mappings, stats)` | Renders the port mapping table with per-port speed, connections, traffic, and action buttons. |
| `_build_echarts_html(cs)` | Builds ECharts line charts with `type: "time"` x-axis (millisecond timestamps, not formatted strings). Supports downsampling and dataZoom defaulting to last 1 hour. |
| `_delete_selected(client, selected_names)` | Batch delete handler: confirms via modal, deletes each selected mapping. |

## UI Components

| Component | Description |
|---|---|
| Summary cards | 4 cards showing mapping count, active connections, total traffic, errors. |
| Mapping table | Sortable table with port, protocol, client, speed, connections, traffic, duration, actions. |
| Detail modal | Per-port popup showing ECharts line chart + per-service stats. |
| Aggregate charts | ECharts area chart for aggregate input/output speed + connections. |
| Add form | Input form for adding new port mappings. |
| Toolbar | Refresh toggle, auto-refresh indicator, delete selected button. |

## Dependencies

- PyWebIO (`put_*`, `use_scope`, `popup`)
- pyecharts (`Line`, `opts`, `JsCode`)
- ECharts JS (served from local `/static/js/echarts.min.js` via `static_bp`)

## Notes

- ECharts is loaded via RequireJS from the local path `/static/js/echarts.min.js` configured in `_ECHARTS_CDN_JS`; there is no CDN fallback.
- Charts use LTTB-style downsampling via `_downsample` (threshold: 1000 points) for performance with large datasets. Previously dead code — `display_max` is now decoupled from `max_history`.
- CSS is inlined in `_CUSTOM_CSS` (no external stylesheet dependency).

## Time Axis

All ECharts charts (main aggregate + per-port detail) use `type: "time"` x-axis:

- **Data format**: Millisecond Unix timestamps (`int(p.timestamp * 1000)`) passed to `add_xaxis()`.
- **Label formatting**: ECharts auto-formats axis labels based on zoom level — shows time when zoomed in, date+time when zoomed out. No manual `_fmt_time()` call needed.
- **Cross-midnight handling**: Native time axis eliminates the category-axis duplicate-label distortion that occurred when `HH:MM:SS` strings repeated across dates.
- **Detail charts**: Inline JS in `_TABLE_INIT_SCRIPT` uses the same `type:'time'` pattern with timestamps from `window._portData` (stored in seconds, converted to ms at render time).

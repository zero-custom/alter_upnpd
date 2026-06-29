# webui_render.py — WebUI HTML/JS Rendering

Renders the GOST WebUI dashboard using PyWebIO components (cards, tables, modals) and ECharts JS for charts. Depends on `webui_format` for data preparation.

## Key Functions

| Function | Description |
|---|---|
| `render_dashboard(client, cs)` | Main dashboard render: summary cards, mapping table, per-port detail modal, aggregate charts. |
| `_render_table(mappings, stats)` | Renders the port mapping table with per-port speed, connections, traffic, and action buttons. |
| `_build_echarts_html(cs)` | Builds ECharts line charts (input/output speed, connections) for all ports plus aggregate. |
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

- ECharts is loaded via RequireJS with a CDN fallback path in `_ECHARTS_CDN_JS`.
- Charts use LTTB-style downsampling via `_downsample` for performance with large datasets.
- CSS is inlined in `_CUSTOM_CSS` (no external stylesheet dependency).

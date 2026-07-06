# alter_upnpd — Handoff

**Version**: v1.3.2 | **Date**: 2026-07-05

## What Was Done

### 1. v1.3.2 — Bug Fixes & Code Cleanup
- **Chart time axis fix**: Switched from `type: "category"` + `HH:MM:SS` to ECharts `type: "time"` + ms timestamps. Eliminates cross-midnight label duplication for charts running 24h+. Applied to both main aggregate and per-port detail charts.
- **Dead code removal**: Deleted `parse_soap_body()` / `build_soap_response()` / `build_fault_response()` from `upnp_soap.py` (unused), `Probe.on()` / `off()` / `active` from `webui_probe.py` (no callers), and stale imports (`get_all_services_stats`, `Optional`, `sys`, `Callable`).
- **Downsampling fix**: `display_max` decoupled from `max_history` — now `min(history_points, 1000)` vs `8640`, so `_downsample()` actually triggers. No more 8640-point full render.
- **`_fmt_time` deduplication**: Removed 2 local copies in `debug_launcher.py`/`webui_probe.py`; both import from `webui_format`.
- **Documentation cleaned up**: All 7 docstrings removed (zero docstring policy); stale references to deleted methods in `upnp_soap.md` updated to `SoapBodyParser.*`.
- **Tests**: 209 passed, 2 pre-existing failures unchanged, zero regressions.

### 2. v1.2.0 — GOST WebUI Dashboard (from previous session)
- **`webui.py`**: PyWebIO + ECharts real-time monitoring dashboard (route `/`).
- Features: summary cards, traffic trend chart, expandable mapping table with per-port charts, add-mapping form, batch delete, 10s auto-refresh.
- Created `static_bp.py` + `static/` directory for local ECharts serving.
- New env vars: `GOST_WEBUI_REFRESH_INTERVAL`, `GOST_WEBUI_HISTORY_POINTS`, `GOST_METRICS_URL`.

### 3. Documentation
- Created bilingual docs for `webui.py`, `webui_render.py`, `webui_format.py`, `upstream_client.py`, `debug_launcher.py`, `lifecycle.md`.
- Added Time Axis section to `webui*.md` documenting `type: "time"` with ms timestamps.
- `CHART_DISTORTION_ANALYSIS.md` in project root with root cause analysis and fix status.

## Project State
- Three SOAP registries: `_SOAP_HANDLERS` (WANIPConnection), `_CIC_HANDLERS` (WANCommonInterfaceConfig), `_L3F_HANDLERS` (Layer3Forwarding).
- `webui.py` fully integrated into Flask app via `pywebio.platform.flask.webio_view`.
- SOAP parsing now via `SoapBodyParser` class (`upnp_soap.py:SoapBodyParser`).
- Downsampling active at 1000-point threshold.
- Zero docstrings policy enforced — all knowledge in `docs/`.
- Previous work (metadata lease, lease cap, TTL cache, upstream IGD sync) preserved.

## Remaining TODOs
- Deploy v1.3.2 to ARM64 container and verify chart after 24h runtime.
- Y-axis P95 clipping (方案 2) — prevent outlier ports from compressing normal range.
- Zero-value port filtering (方案 4) — skip 100% zero data series.

## Key Files
- `alter_upnpd/AGENTS.md` — project-only agent guide
- `alter_upnpd/docs/` — 26 program doc files (13 English + 13 Chinese) + 2 handoff files
- `alter_upnpd/app/` — 10 Python source files + `static/` + `xml/`
- `CHART_DISTORTION_ANALYSIS.md` — chart distortion investigation and fix tracking

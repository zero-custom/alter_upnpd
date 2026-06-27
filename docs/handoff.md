# alter_upnpd — Handoff

## What Was Done

### 1. AGENTS.md Created and Refined
- Wrote initial `AGENTS.md` with architecture, directory structure, SOAP registries, commands, testing, env vars, anti-patterns, SSDP constants.
- Refined iteratively: added key facts, corrected XML file descriptions, clarified SOAP registry structure, added known limitations.
- Updated for v1.2.0: added `webui.py` to structure, lookup table, API routes, and configuration.

### 2. Chinese Documentation (`.zh.md`)
- Created Chinese versions (`*.zh.md`) of all 7 source documentation files alongside their English counterparts:
  - `app`, `config`, `gost_client`, `gunicorn_config`, `ssdp_responder`, `stun_client`, `upnp_soap`
- Decision: retain both `.md` (English) and `.zh.md` (Chinese) as sibling files.

### 3. Handoff Docs
- Created `handoff.md` (English) and `handoff.zh.md` (Chinese) in `docs/` for session continuity.

### 4. v1.2.0 — GOST WebUI Dashboard
- **`webui.py`**: PyWebIO + ECharts real-time monitoring dashboard (route `/`).
- Features: summary cards, traffic trend chart, expandable mapping table with per-port charts, add-mapping form, batch delete, 10s auto-refresh.
- CSS/JS fixes: zebra striping (`_applyZebra()`), detail row width (`_countTableCols()` returns 16), `.markdown-body` prefix for specificity.
- Created `static_bp.py` + `static/` directory for local ECharts serving.
- New env vars: `GOST_WEBUI_REFRESH_INTERVAL`, `GOST_WEBUI_HISTORY_POINTS`, `GOST_METRICS_URL`.

## Project State
- Three SOAP registries: `SOAP_ACTIONS` (WANIPConnection), `CIC_ACTIONS` (WANCommonInterfaceConfig), `L3F_ACTIONS` (Layer3Forwarding).
- `webui.py` fully integrated into Flask app via `pywebio.platform.flask.webio_view`.
- `AGENTS.md`, `.env.example`, and all program docs updated for v1.2.0.
- Previous session work (metadata lease, lease cap, TTL cache, upstream IGD sync) preserved.

## Key Files
- `alter_upnpd/AGENTS.md` — project-only agent guide
- `alter_upnpd/docs/` — 26 program doc files (13 English + 13 Chinese) + 2 handoff files
- `alter_upnpd/app/` — 10 Python source files + `static/` + `xml/`

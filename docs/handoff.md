# alter_upnpd — Handoff

## What Was Done

### 1. AGENTS.md Created and Refined
- Wrote initial `AGENTS.md` with architecture, directory structure, SOAP registries, commands, testing, env vars, anti-patterns, SSDP constants.
- Refined iteratively based on feedback: added critical facts, corrected XML file descriptions, clarified SOAP registry structure, added known limitations section.

### 2. Chinese Documentation (`.zh.md`)
- Created Chinese versions (`*.zh.md`) of all 7 source documentation files alongside their English counterparts:
  - `app`, `config`, `gost_client`, `gunicorn_config`, `ssdp_responder`, `stun_client`, `upnp_soap`
- Decision: retain both `.md` (English) and `.zh.md` (Chinese) as sibling files. No overwrites.

### 3. Handoff Docs
- Created `handoff.md` (English) and `handoff.zh.md` (Chinese) in `docs/` for session continuity.

## Project State
- Three SOAP registries: `SOAP_ACTIONS` (WANIPConnection), `CIC_ACTIONS` (WANCommonInterfaceConfig), `L3F_ACTIONS` (Layer3Forwarding).
- `AGENTS.md`, `.env.example`, and all program docs cleaned and ready.
- Previous session work (metadata lease, lease cap, TTL cache, P0/P1/P2 fixes, namespace fixes, SSDP completion) preserved.

## Key Files
- `alter_upnpd/AGENTS.md` — project-only agent guide
- `alter_upnpd/docs/` — 14 program doc files (7 English + 7 Chinese) + 2 handoff files
- `alter_upnpd/app/` — 7 Python source files + xml/ directory

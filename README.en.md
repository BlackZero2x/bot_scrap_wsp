# au_tl_bot

*[Versión en español](./README.md)*

Automation for extracting data from the TOA portal (Oracle Field Service, `telefonica-pe.etadirect.com`) into SQL Server, with a WhatsApp bot ("Yugi Backoffice") that lets salespeople check the real-time status of a work order (FE) from a group chat.

## Main components

| Component | Description |
|---|---|
| `scrapper.py` | Main bot (Selenium): logs into TOA, searches pending FEs, and extracts ~35 fields per screen into `pbi2.fija_data_toa`. |
| `toa_client.py` | Hybrid client (Playwright + direct HTTP) against TOA's internal sync endpoint — under validation as a replacement for DOM scraping. |
| `query_fe_filter.py` | Resolves the list of pending FEs to process (VENTORY Postgres + eAuren, filtered against `pbi2.fija_data_toa`). |
| `whatsapp_server/` | "Yugi Backoffice" WhatsApp bot — replies to `/estado FE-XXXXXXXXXX` in zonal group chats. |
| `consultar_estado_fe.py` | Read-only cascade that resolves an FE's status: VENTORY → eAuren → local TOA cache → on-demand lookup. |
| `toa_servicio_busqueda.py` | HTTP service holding a persistent TOA session, used by the WhatsApp listener for on-demand lookups. |
| `mantenimiento_continuo.py` | Discovers new FEs and re-checks transient statuses every 15 minutes. |

Full architecture, per-module data flow, and design decisions are documented in [`CLAUDE.md`](./CLAUDE.md) (Spanish).

## Requirements

- Python 3.10+
- Node.js (for `whatsapp_server/`)
- **ODBC Driver 17 for SQL Server**
- Access to SQL Server (`eAuren`, `pbi2`), Postgres (VENTORY), and the TOA portal

## Setup

```bash
pip install -r requirements.txt
playwright install chromium

cd whatsapp_server
npm install
```

Copy `.env.example` to `.env` and fill in real credentials (never committed):

```bash
cp .env.example .env
```

For the WhatsApp bot, also copy:

```bash
cp whatsapp_server/config.json.example whatsapp_server/config.json
```

## Usage

```bash
# Main TOA -> SQL Server extraction bot
python scrapper.py

# Test the hybrid client in isolation
python toa_client.py FE-1128653298

# List pending FEs
python query_fe_filter.py

# WhatsApp bot ("Yugi Backoffice")
cd whatsapp_server && node wa_toa_server.js

# Test the status cascade without WhatsApp
python consultar_estado_fe.py FE-1128653298

# TOA on-demand lookup HTTP service (port 8004)
python toa_servicio_busqueda.py --http

# Discover new FEs + re-check transient statuses
python mantenimiento_continuo.py
```

See [`CLAUDE.md`](./CLAUDE.md) for the rest of the commands, the bot's working-hours window, and details on each database and module.

## Security

- All credentials live in `.env` (not versioned) — `.env.example` documents the required variables without real values.
- `whatsapp_server/config.json` (the bot's real phone number) is also not versioned — use `config.json.example` as a template.
- Do not commit diagnostic captures, customer data exports, or WhatsApp sessions — see `.gitignore`.

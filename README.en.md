# au_tl_bot

*[Versión en español](./README.md)*

Automation for extracting data from the client's sales-lookup web portal into SQL Server, with a Python backoffice agent that lets salespeople check the real-time status of a sale code from a WhatsApp chat.

## Main components

| Component | Description |
|---|---|
| `scrapper.py` | Main bot (Selenium): logs into the sales-lookup portal, searches pending sale codes, and extracts ~35 fields per screen into SQL Server. |
| `toa_client.py` | Hybrid client (Playwright + direct HTTP) against the portal's internal sync endpoint — under validation as a replacement for DOM scraping. |
| `query_fe_filter.py` | Resolves the list of pending sale codes to process (sales-registration app + legacy database, filtered against the destination table). |
| `whatsapp_server/` | Python backoffice agent — replies to `/estado <code>` in WhatsApp group chats. |
| `consultar_estado_fe.py` | Read-only cascade that resolves a sale code's status: sales-registration app → legacy database → local cache → on-demand lookup. |
| `toa_servicio_busqueda.py` | HTTP service holding a persistent session against the sales-lookup portal, used by the WhatsApp agent for on-demand lookups. |
| `mantenimiento_continuo.py` | Discovers new sale codes and re-checks transient statuses every 15 minutes. |

Full architecture, per-module data flow, and design decisions are documented in an internal technical notes file (not versioned).

## Requirements

- Python 3.10+
- Node.js (for `whatsapp_server/`)
- **ODBC Driver 17 for SQL Server**
- Access to SQL Server, Postgres (sales-registration app), and the client's sales-lookup web portal

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

For the WhatsApp agent, also copy:

```bash
cp whatsapp_server/config.json.example whatsapp_server/config.json
```

## Usage

```bash
# Main extraction bot -> SQL Server
python scrapper.py

# Test the hybrid client in isolation
python toa_client.py SAMPLE-CODE

# List pending sale codes
python query_fe_filter.py

# Python backoffice agent (WhatsApp)
cd whatsapp_server && node wa_toa_server.js

# Test the status cascade without WhatsApp
python consultar_estado_fe.py SAMPLE-CODE

# On-demand lookup HTTP service (port 8004)
python toa_servicio_busqueda.py --http

# Discover new sale codes + re-check transient statuses
python mantenimiento_continuo.py
```

## Security

- All credentials live in `.env` (not versioned) — `.env.example` documents the required variables without real values.
- `whatsapp_server/config.json` (the agent's real phone number) is also not versioned — use `config.json.example` as a template.
- Do not commit diagnostic captures, customer data exports, or WhatsApp sessions — see `.gitignore`.

# au_tl_bot

*[English version](./README.en.md)*

Automatización de extracción de datos del portal TOA (Oracle Field Service, `telefonica-pe.etadirect.com`) hacia SQL Server, con un bot de WhatsApp ("Yugi Backoffice") que permite a vendedores consultar el estado de una FE en tiempo real.

## Componentes principales

| Componente | Descripción |
|---|---|
| `scrapper.py` | Bot principal (Selenium): login en TOA, búsqueda de FEs pendientes y extracción de ~35 campos por pantalla hacia `pbi2.fija_data_toa`. |
| `toa_client.py` | Cliente híbrido (Playwright + HTTP directo) al endpoint interno de sync de TOA — en validación como reemplazo del scraping por DOM. |
| `query_fe_filter.py` | Resuelve la lista de FEs pendientes de procesar (VENTORY Postgres + eAuren, con delta contra `pbi2.fija_data_toa`). |
| `whatsapp_server/` | Bot de WhatsApp "Yugi Backoffice" — responde `/estado FE-XXXXXXXXXX` en grupos de zonal. |
| `consultar_estado_fe.py` | Cascada de solo lectura que resuelve el estado de una FE: VENTORY → eAuren → caché local TOA → búsqueda puntual. |
| `toa_servicio_busqueda.py` | Servicio HTTP con sesión TOA persistente, consumido por el listener de WhatsApp para búsquedas puntuales. |
| `mantenimiento_continuo.py` | Descubre FEs nuevos y re-verifica estados transitorios cada 15 min. |

La arquitectura completa, el flujo de cada módulo y las decisiones de diseño están documentadas en [`CLAUDE.md`](./CLAUDE.md).

## Requisitos

- Python 3.10+
- Node.js (para `whatsapp_server/`)
- **ODBC Driver 17 for SQL Server**
- Acceso a SQL Server (`eAuren`, `pbi2`), Postgres (VENTORY) y al portal TOA

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium

cd whatsapp_server
npm install
```

Copiar `.env.example` a `.env` y completar las credenciales reales (nunca se commitea):

```bash
cp .env.example .env
```

Para el bot de WhatsApp, copiar también:

```bash
cp whatsapp_server/config.json.example whatsapp_server/config.json
```

## Uso

```bash
# Bot principal de extracción TOA → SQL Server
python scrapper.py

# Probar el cliente híbrido de forma aislada
python toa_client.py FE-1128653298

# Consultar FEs pendientes
python query_fe_filter.py

# Bot de WhatsApp "Yugi Backoffice"
cd whatsapp_server && node wa_toa_server.js

# Probar la cascada de estado sin WhatsApp
python consultar_estado_fe.py FE-1128653298

# Servicio HTTP de búsqueda puntual en TOA (puerto 8004)
python toa_servicio_busqueda.py --http

# Descubrimiento de FEs nuevos + re-verificación de transitorios
python mantenimiento_continuo.py
```

Ver [`CLAUDE.md`](./CLAUDE.md) para el resto de comandos, la ventana laboral del bot, y el detalle de cada base de datos y módulo.

## Seguridad

- Todas las credenciales viven en `.env` (no versionado) — `.env.example` documenta las variables necesarias sin valores reales.
- `whatsapp_server/config.json` (número real del bot) tampoco se versiona — usar `config.json.example` como plantilla.
- No commitear capturas de diagnóstico, exports de datos de clientes ni sesiones de WhatsApp — ver `.gitignore`.

# au_tl_bot

*[English version](./README.en.md)*

Automatización de extracción de datos de la web de consulta de ventas del cliente hacia SQL Server, con un agente de Python de backoffice que permite a vendedores consultar el estado de un código de venta en tiempo real vía WhatsApp.

## Componentes principales

| Componente | Descripción |
|---|---|
| `scrapper.py` | Bot principal (Selenium): login en la web de consulta, búsqueda de códigos de venta pendientes y extracción de ~35 campos por pantalla hacia SQL Server. |
| `toa_client.py` | Cliente híbrido (Playwright + HTTP directo) al endpoint interno de sincronización de la web de consulta — en validación como reemplazo del scraping por DOM. |
| `query_fe_filter.py` | Resuelve la lista de códigos de venta pendientes de procesar (App de registro de ventas + base de datos legado, con delta contra la tabla destino). |
| `whatsapp_server/` | Agente Python de backoffice — responde `/estado <código>` en grupos de WhatsApp. |
| `consultar_estado_fe.py` | Cascada de solo lectura que resuelve el estado de un código de venta: App de registro de ventas → base de datos legado → caché local → búsqueda puntual. |
| `toa_servicio_busqueda.py` | Servicio HTTP con sesión persistente contra la web de consulta, usado por el agente de WhatsApp para búsquedas puntuales. |
| `mantenimiento_continuo.py` | Descubre códigos de venta nuevos y re-verifica estados transitorios cada 15 min. |

La arquitectura completa, el flujo de cada módulo y las decisiones de diseño están documentadas en un archivo de notas técnicas interno (no versionado).

## Requisitos

- Python 3.10+
- Node.js (para `whatsapp_server/`)
- **ODBC Driver 17 for SQL Server**
- Acceso a SQL Server, Postgres (App de registro de ventas) y a la web de consulta de ventas del cliente

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

Para el agente de WhatsApp, copiar también:

```bash
cp whatsapp_server/config.json.example whatsapp_server/config.json
```

## Uso

```bash
# Bot principal de extracción → SQL Server
python scrapper.py

# Probar el cliente híbrido de forma aislada
python toa_client.py CODIGO-EJEMPLO

# Consultar códigos de venta pendientes
python query_fe_filter.py

# Agente Python de backoffice (WhatsApp)
cd whatsapp_server && node wa_toa_server.js

# Probar la cascada de estado sin WhatsApp
python consultar_estado_fe.py CODIGO-EJEMPLO

# Servicio HTTP de búsqueda puntual (puerto 8004)
python toa_servicio_busqueda.py --http

# Descubrimiento de códigos nuevos + re-verificación de transitorios
python mantenimiento_continuo.py
```

## Seguridad

- Todas las credenciales viven en `.env` (no versionado) — `.env.example` documenta las variables necesarias sin valores reales.
- `whatsapp_server/config.json` (número real del bot) tampoco se versiona — usar `config.json.example` como plantilla.
- No commitear capturas de diagnóstico, exports de datos de clientes ni sesiones de WhatsApp — ver `.gitignore`.

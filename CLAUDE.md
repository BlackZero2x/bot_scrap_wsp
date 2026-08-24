# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos comunes

```bash
# Instalar dependencias
pip install -r requirements.txt
playwright install chromium

# Ejecutar el bot principal
python scrapper.py

# Probar el cliente híbrido TOA de forma aislada (login + 1-N FEs)
python toa_client.py FE-1128653298

# Ejecutar el script de control de horario
python main.py

# Migrar un CSV existente a SQL Server
python migracion_masiva.py

# Consultar FEs pendientes (VENTORY + delta contra pbi2.fija_data_toa)
python query_fe_filter.py

# Probar solo la lectura de VENTORY (Google Sheet)
python scripts_db/ventory_sheet.py

# Bot de WhatsApp "Yugi Backoffice" — consultas /estado FE-...
cd whatsapp_server && node wa_toa_server.js

# Probar la cascada de consulta de estado de forma aislada (sin WhatsApp)
python consultar_estado_fe.py FE-1128653298

# Servicio HTTP de búsqueda puntual en TOA (puerto 8004), consumido por el listener de WhatsApp
python toa_servicio_busqueda.py --http

# Refrescar manualmente el caché local de estado TOA (mes actual)
python refrescar_cache_toa.py

# Buscar FEs nuevos de VENTORY + re-verificar transitorios en TOA
python mantenimiento_continuo.py
```

Requiere **ODBC Driver 17 for SQL Server** instalado en el sistema Windows.

## Arquitectura

El bot automatiza la extracción de datos del portal TOA (telefonica-pe.etadirect.com) y los persiste en SQL Server.

> **Reenfoque en curso (2026-08):** el envío de resultados vía bot de Telegram (`bot_tl.py`, `main.py`) queda en stand-by. El foco actual es la extracción TOA → SQL Server usando VENTORY como fuente de FEs pendientes (ver abajo).
>
> **Migración de scraping en curso (2026-08):** el bot está migrando de leer el DOM con Selenium a un **cliente híbrido** (`toa_client.py`, Playwright + HTTP directo) que llama al endpoint interno de sync de TOA. Ver sección "Cliente híbrido TOA" abajo. `scrapper.py::BotTOA` (Selenium puro) sigue siendo el flujo productivo hasta que la migración se valide e integre a `start_bot()`.
>
> **Bot de WhatsApp "Yugi Backoffice" (2026-08-19 en adelante):** nuevo canal para que los vendedores consulten el estado de una FE directo desde WhatsApp con `/estado FE-XXXXXXXXXX`. Vive en `whatsapp_server/` y reutiliza el cliente híbrido TOA (`toa_client.py`) para las búsquedas puntuales. Ver sección "Bot de WhatsApp — Yugi Backoffice" abajo.

### Flujo principal (`scrapper.py`, Selenium — productivo)

1. `filter_query()` (`query_fe_filter.py`) — obtiene la lista de FEs pendientes desde **VENTORY** (Google Sheet, ver abajo), excluyendo los ya procesados en `pbi2.dbo.fija_data_toa`.
2. `particionar_fe()` — divide la lista en grupos de 300.
3. `BotTOA` — instancia Selenium en modo headless, hace login en TOA, busca cada FE, extrae ~35 campos por pantalla, guarda en CSV y migra al SQL Server.
4. `handler_data()` (`date_parser.py`) — normaliza fechas del diccionario extraído antes de insertar a BD.
5. `clean_table()` (`scripts_db/data_extraida.py`) — elimina duplicados en `fija_data_toa` al final de cada grupo.

El bot opera solo dentro de ventanas horarias: 06:30–13:00 y 14:00–20:30. Fuera de ese rango espera o termina.

### Cliente híbrido TOA (`toa_client.py`, Playwright + HTTP — en validación)

Reemplaza la lectura del DOM por el endpoint interno de sincronización que usa el propio frontend de OFSC (Oracle Field Service). Flujo:

1. `login_y_obtener_sesion()` — abre Playwright (headless, con reintentos), hace login, y captura de una request real hacia `?m=sync&a=write` los parámetros de sesión (`trust`, `x-ofs-csrf-secure`, `dv`, `u`) que **no rotan durante toda la sesión**. Cierra el navegador al terminar.
2. `buscar_fe(sesion, fe)` — `POST /index.php?m=search&a=search` (HTTP puro, sin navegador) con `searchValue=FE-...`, devuelve `aid` (ID interno de actividad), `pid` (id del recurso/técnico dueño) y `date`.
3. `obtener_detalle_actividad(sesion, aid, fecha, pid)` — `POST /?m=sync&a=write` con `requestedAid`/`requestedDate` y el **`pid` del resultado de búsqueda** (no el de sesión — usar el equivocado devuelve `delta.Activity` vacío). Trae el detalle completo de la actividad en JSON (~260 campos), sin telemetría de comportamiento (esa solo la usa el endpoint de `sync` en sus otras variantes, no esta).
4. `scripts_db/campo_mapper.py::mapear_activity_a_columnas()` — traduce el JSON de actividad a las 137 columnas nuevas de `fija_data_toa` (prefijo `toa_`, ver `columnas_nuevas_propuestas.json`), usando `key_json` como puente.
5. `mapeo_campos_clasicos.json` (raíz) — equivalencia confirmada entre los ~19 campos "clásicos" de `dict_info_cod` y sus keys reales en el JSON de sync (`fecha_cita` es el único aún sin resolver — no viene directo en `delta.Activity`). `fecha_agendamiento`/`franja_agendamiento` mapean a las keys `2456`/`2457` (corregido 2026-08-21 — las keys previas `XA_FECHA_AGENDA`/`XA_TIMESLOT_AGENDA` no existen en el JSON real, siempre devolvían `None`).

Investigación que sustenta este diseño: `diagnostico_request_sync.json` (no comiteado, contiene tokens de sesión) — capturado con `scripts_db/investigar_request_sync.py`.

### Bot de WhatsApp — Yugi Backoffice (`whatsapp_server/`)

Bot de WhatsApp que responde `/estado FE-XXXXXXXXXX` en los grupos de zonal, citando el mensaje del vendedor. Solo procesa mensajes de **grupo**, nunca DMs (fan-out a contactos es el patrón de spam más vigilado por Meta).

**Componentes:**

| Archivo | Rol |
|---------|-----|
| `whatsapp_server/wa_toa_server.js` | Cliente whatsapp-web.js, sesión persistente (`session_data/`) |
| `whatsapp_server/wa_toa_listener.js` | Escucha `/estado ...` (3 formatos tolerados, ver comentario en el archivo), invoca la cascada Python, responde |
| `consultar_estado_fe.py` | Cascada de solo lectura: VENTORY → eAuren → caché local TOA |
| `cache_toa.py` | Caché SQLite local (`cache_toa.db`) — espejo de `pbi2.fija_data_toa` acotado al mes actual |
| `refrescar_cache_toa.py` | Relee `pbi2.fija_data_toa` (mes actual) y reemplaza el caché completo |
| `toa_servicio_busqueda.py` | Servicio HTTP (puerto 8004) con sesión TOA persistente — búsqueda puntual cuando el FE nunca se buscó en TOA |
| `mantenimiento_continuo.py` | Busca FEs nuevos de VENTORY + re-verifica transitorios (Iniciado/Pendiente/Enviado/Suspendido) cada 15 min |

**Cascada de `consultar_estado_fe.py`** (solo lectura, sin conocimiento de TOA/HTTP):

1. **VENTORY** (Postgres) — gate de acceso. Si el FE no está registrado (mes actual + anterior), responde `"La FE no está registada en VENTORY, porfa registralo, espera unos minutos y vuelve a intentarlo"` y corta ahí.
2. **eAuren** (D-1) — resuelve `Cerrado` (instalado, con fecha) y `Cancelado` directo. `Enviado` u otros estados no definitivos pasan al paso 3.
3. **Caché local SQLite** (`cache_toa.py`) — nunca toca `pbi2` en vivo (mitiga fallos intermitentes SQL 18456 de `adminpbi2`). Resuelve `Iniciada` (con fecha+franja+intervalo de agenda si existen) o motivo de cancelación.
   - Si el FE no está en caché: responde `"FE aun no pasa a TOA"`. El listener (`wa_toa_listener.js`, no este módulo) es quien decide disparar la búsqueda puntual real (paso 3b) contra `toa_servicio_busqueda.py --http`, y si encuentra algo, vuelve a llamar la cascada para releer el dato ya guardado.

**Servicio de búsqueda TOA** (`toa_servicio_busqueda.py --http`, puerto 8004): mantiene una sesión TOA autenticada en memoria (login Playwright una sola vez), cola secuencial en memoria (un solo worker, evita ráfagas de requests). Auto-relogin tras 2 fallos consecutivos de búsqueda real — necesario porque la cuenta `TOA_PORTAL_USERNAME` es compartida por varios backoffices humanos; si alguien más se loguea marcando "cerrar sesiones anteriores", invalida la sesión del bot sin que el proceso muera según el SO. Renovación proactiva de sesión cada 4h (`RENOVACION_SESION_SEG`) — una sesión vieja (~19h+) empieza a devolver "no encontrado" de forma silenciosa para FEs nuevos sin lanzar excepción, así que el auto-relogin por fallos consecutivos nunca lo detectaba (confirmado 2026-08-21/22). Log persistente en `logs/toa_servicio_busqueda.log`.

> **Ventana laboral obligatoria (2026-08-24):** este servicio (y `mantenimiento_continuo.py`, que también hace login TOA) **solo debe operar de 8:00 a 20:00** — mantener una sesión TOA autenticada 24/7 es una huella de actividad no-humana innecesaria y riesgosa frente a Seguridad de Telefónica (confirmado en producción: el proceso llegó a correr casi 48h continuas antes de este fix). `_dentro_de_ventana_laboral()` en `toa_servicio_busqueda.py` es la fuente de verdad de la ventana; `_correr_servidor_http()` rechaza arrancar fuera de ella y un hilo (`_vigilar_cierre_ventana`) se autocierra al llegar las 20:00 como defensa en profundidad. `resucitar_servicio_toa.ps1` nunca revive el servicio fuera de la ventana (y lo apaga si lo encuentra vivo fuera de hora). El listener de WhatsApp (`wa_toa_listener.js::_dentroDeVentanaBusqueda()`) sabe que el servicio no está disponible fuera de esa ventana: si el paso 3b haría falta, responde con **silencio total** (decisión explícita del usuario, no un mensaje alternativo).

**Infraestructura de auto-recuperación** (Programador de tareas de Windows, patrón: verificar `/health` o proceso vivo, matar zombie si existe, relanzar):

| Tarea | Ventana | Intervalo | Script | Qué vigila |
|---|---|---|---|---|
| ResucitarYugi | 24/7 | 5 min | `whatsapp_server/resucitar_yugi.ps1` | `wa_toa_server.js` (puerto 8003 `/health`) |
| RefrescarCacheTOA | 24/7 | 10 min | `refrescar_cache_toa.py` | — (job de refresco, solo SQL Server, sin login TOA) |
| MantenimientoContinuoTOA | 8:00–20:00 | 15 min | `mantenimiento_continuo.py` | — (job de descubrimiento/re-verificación, hace login TOA) |
| ResucitarServicioTOA | 8:00–20:00 | 5 min | `resucitar_servicio_toa.ps1` | `toa_servicio_busqueda.py --http` (puerto 8004 `/health`; fuera de ventana apaga el proceso si lo encuentra vivo en vez de revivirlo) |

> **Incidente en curso (2026-08-24) — bug CONFIRMADO de whatsapp-web.js, no de este proyecto:** Yugi empezó a fallar intermitentemente en `msg.getChat()` (error interno minificado `"r: r"`, dentro de `Client.getChatById` → `window.WWebJS.getChat`, `whatsapp-web.js/src/Client.js:1754`), a veces escalando a un loop de reinicios. Se descartó metódicamente: (1) código propio — reproducido incluso revirtiendo TODOS los cambios de la sesión a la forma más simple; (2) perfil de Chrome corrupto — reproducido con `session_data` completamente limpio y re-autenticado desde cero; (3) cambio de versión local — `whatsapp-web.js` en el mismo commit desde el 23/08, versión de WA Web cacheada sin cambios desde el 21/08, Chrome del sistema sin cambios desde el 20/08. Confirmado por búsqueda externa: es un bug activo y documentado por la comunidad (GitHub issues [#201838](https://github.com/wwebjs/whatsapp-web.js/issues/201838) y [#201845](https://github.com/wwebjs/whatsapp-web.js/issues/201845), julio 2026, mismo error exacto, persiste incluso limpiando caché/sesión), coincidente con el rollout de **"WhatsApp Web Calling"** de Meta (28/07/2026) — Meta despliega este tipo de cambios de forma gradual por cuenta/región del lado del servidor, sin cambiar ningún número de versión visible del cliente, lo que explica que la cuenta funcionara bien varios días y luego empezara a fallar sin que nada local hubiera cambiado. **Sin fix estable publicado por la librería a la fecha.** Mitigación aplicada (no resuelve la causa, solo contiene el impacto): `wa_toa_listener.js::_getChatConReintento()` reintenta `getChat()` hasta 3 veces con 2s de espera antes de darlo por fallido; si aun así falla `FALLOS_GETCHAT_PARA_REINICIAR` (3) veces seguidas, notifica a `wa_toa_server.js` vía el callback `onFalloRepetido` para disparar `_reiniciarCliente()`. Revisar los issues de GitHub periódicamente por si la librería publica un fix.

Yugi (`wa_toa_server.js`) en sí sigue disponible 24/7 y responde `/estado` a cualquier hora — la ventana laboral solo restringe el servicio de búsqueda puntual en TOA (paso 3b) y el descubrimiento proactivo, no la disponibilidad del bot de WhatsApp.

Todas con `ExecutionTimeLimit` ajustado a su propio ciclo (no el default de 72h) para evitar un colgado silencioso bloqueando corridas futuras.

### VENTORY — fuente de FEs pendientes

VENTORY es la app interna de AUREN donde los vendedores registran sus ventas (código FE y petición). La fuente real es **Postgres (`ventas_db`, tabla `ventas`)** — no el Google Sheet (ver nota de migración abajo).

- `query_fe_filter.py::_resolver_fes_ventory()` y `mantenimiento_continuo.py` resuelven FEs activos combinando **eAuren** (`scripts_db/peticiones_activas_mes.py::obtener_peticiones_activas_mes()`, peticiones del mes en `fija_registros_totales`/`fija_altas`) con **VENTORY Postgres** (`ventas.codigo_seguridad` = FE, `ventas.codigo_seguridad_2` = `eAuren.peticion` — puente confirmado cruzando datos reales, sesión 2026-08-19).
- Credenciales vía `.env`: `host`, `port`, `tabla`, `user`, `password` (sin prefijo `VENTORY_` — nombres genéricos históricos), consumidas por `config.py::engine_ventory_pg()`.
- `consultar_estado_fe.py` (cascada de Yugi) también usa `engine_ventory_pg()` directo como gate de acceso (paso 1 de la cascada).

> **Migración completada (2026-08-24):** el Google Sheet **"Integratel-GrupoAuren"** (hoja `REG_VTAS_BBDD`, `scripts_db/ventory_sheet.py::obtener_ventas_ventory()`) quedó **legado, sin uso en ningún flujo productivo** — `query_fe_filter.py` migró de leer el Sheet a resolver FEs desde Postgres (mismo patrón que ya usaba `mantenimiento_continuo.py`). Causa del cambio: `config.py` exigía `VENTORY_SHEET_ID`/`VENTORY_SHEET_GID` como variables obligatorias (`os.environ[...]`) aunque el `.env` de producción nunca las tuvo tras la migración a Postgres — esto rompía con `KeyError` cualquier script que importara `config.py`, incluyendo `consultar_estado_fe.py` (que ni siquiera usa el Sheet), causando que Yugi respondiera "FE aun no pasa a TOA" para toda consulta sin importar el FE real. Ahora esas variables son opcionales (`os.getenv`, default `None`) — solo hacen falta si se vuelve a usar `ventory_sheet.py` explícitamente.

### Bases de datos SQL Server

| Base | Propósito |
|------|-----------|
| `eAuren` (usuario `eauren`) | Legado: tabla `fija_controlnet_detallado`, ya no es la fuente principal de FEs (ver VENTORY arriba) |
| `pbi2` (usuario `adminpbi2`) | Destino: tabla `fija_data_toa` con los datos extraídos de TOA |

### Módulos clave

| Archivo | Rol |
|---------|-----|
| `scrapper.py` | Clase `BotTOA` + orquestación principal |
| `query_fe_filter.py` | Filtra qué FEs procesar (delta entre VENTORY y destino) |
| `scripts_db/ventory_sheet.py` | Lectura de FEs pendientes desde el Sheet VENTORY (`REG_VTAS_BBDD`) |
| `date_parser.py` | Normaliza fechas del dict scrapeado para inserción |
| `migracion_masiva.py` | Carga masiva de CSVs existentes a SQL Server |
| `scripts_db/fe_consultar.py` | Consultas legado sobre `eAuren` |
| `scripts_db/data_extraida.py` | Consultas/limpieza sobre `pbi2.fija_data_toa` |

### Extracción de campos TOA

`BotTOA.scrapping_information()` usa dos estrategias:
- **IDs directos**: elementos localizados por `id_index_{N}` (diccionario `dict_info_cod`)
- **Selectores CSS especiales**: campos con `aria-describedby` o clases específicas

El campo `estado_general` se parsea desde el texto del resultado de búsqueda (formato `"... - ... - ESTADO"`).

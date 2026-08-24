"""
Servicio de búsqueda puntual en TOA — paso 3b del diseño de arquitectura del
bot WhatsApp (sesión 2026-08-19/20). Se dispara cuando consultar_estado_fe.py
llega al final de la cascada (VENTORY -> eAuren -> pbi2.fija_data_toa) sin
encontrar nada: el FE nunca fue buscado en TOA todavía.

Mantiene una sesión TOA autenticada en memoria (login con Playwright, una
sola vez) y resuelve cada búsqueda por HTTP puro vía toa_client.py — sin
volver a abrir navegador por FE. Guarda el resultado en pbi2.fija_data_toa
antes de devolverlo, para que la próxima consulta del mismo FE ya lo
encuentre cacheado (paso 3 normal, sin volver a tocar TOA).

Este mismo servicio es el que reutilizará scrapper.py en su fase de
mantenimiento continuo (cada 15 min, ver diseño) — un solo componente,
una sola sesión TOA, dos consumidores.

Modo --http expone POST /buscar {"fe": "FE-..."} como servidor síncrono
(http.server de la librería estándar, sin dependencias nuevas) — es lo que
consume wa_toa_listener.js: hace login una sola vez al arrancar, y cada
request bloquea hasta 60s (ventana ya acordada) mientras la cola procesa esa
búsqueda. No hay callback separado: "no tiene por qué ser rápido, tenemos
la ventana de un minuto" — más simple que un patrón async con aviso aparte.

Uso:
    python toa_servicio_busqueda.py --http          (servidor HTTP, puerto 8004)
    python toa_servicio_busqueda.py --serve          (modo interactivo por stdin, pruebas)
    python toa_servicio_busqueda.py FE-1128653298    (puntual, login por request, solo pruebas)
"""
import json
import sys
import threading
import time
from datetime import datetime, time as dt_time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# El proceso --http corre como Start-Process -WindowStyle Hidden (ver
# resucitar_servicio_toa.ps1) — su stdout no queda capturado en ningún
# archivo, así que un comportamiento raro en un proceso de larga duración
# (ej. resultados "no encontrado" sospechosamente rápidos) era indiagnosticable
# sin reiniciar a ciegas (confirmado 2026-08-21). Log persistente propio,
# mismo patrón que mantenimiento_continuo.py.
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "toa_servicio_busqueda.log"


def _log(mensaje: str) -> None:
    print(mensaje)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensaje}\n")


# Ventana laboral (2026-08-24, confirmado con el usuario): este servicio
# mantiene una sesión TOA autenticada en memoria de forma continua — antes
# corría 24/7 (confirmado en producción: procesos de casi 48h seguidas),
# lo cual es una huella de actividad no-humana innecesaria y riesgosa de
# cara a Seguridad de Telefónica (un login fuera de todo horario laboral
# es exactamente el tipo de señal que delata automatización). El servicio
# ahora solo debe operar de 8:00 a 20:00 — el Task Scheduler de Windows es
# quien arranca/detiene el proceso en esos bordes (ver ResucitarServicioTOA
# y la tarea de arranque), pero este guard es la última línea de defensa
# por si el proceso se lanza manualmente o con retraso fuera de ventana.
VENTANA_INICIO = dt_time(8, 0)
VENTANA_FIN = dt_time(20, 0)


def _dentro_de_ventana_laboral() -> bool:
    ahora = datetime.now().time()
    return VENTANA_INICIO <= ahora < VENTANA_FIN


import pandas as pd
from sqlalchemy import text

from config import engine_toa
from toa_client import SesionTOA, buscar_y_extraer_fe, login_y_obtener_sesion
from scripts_db.campos_clasicos_mapper import mapear_campos_clasicos
from scripts_db.campo_mapper import mapear_activity_a_columnas

HTTP_PORT = 8004


def _guardar_en_pbi2(activity_json: dict, fe_buscado: str, dni_vendedor: str = None) -> None:
    """
    Combina campos clásicos + columnas nuevas (mismo patrón que
    scripts_db/insertar_verificacion_hibrido.py) e inserta la fila en
    pbi2.dbo.fija_data_toa. dni_vendedor queda None si no se provee — la
    tabla ventas de VENTORY Postgres no trae ese dato directamente (a
    diferencia del Sheet REG_VTAS_BBDD), pendiente de resolver el cruce si
    se necesita más adelante.

    Borra cualquier fila previa con el mismo work_order antes de insertar —
    encontrado en pruebas reales (2026-08-20): si el listener dispara el
    paso 3b dos veces para el mismo FE (ej. por un fallo de lectura
    intermitente en la cascada), sin este borrado quedaban filas duplicadas
    en fija_data_toa, y pd.read_sql() sobre "WHERE work_order = ?" sin
    ORDER BY no garantiza determinismo sobre cuál de las duplicadas devuelve.

    DELETE + INSERT corren dentro de la MISMA transacción (una sola
    conexión, un solo commit) — antes eran dos transacciones separadas
    (el DELETE comiteaba y cerraba su conexión antes de que to_sql() abriera
    la suya para el INSERT), dejando una ventana real donde una lectura
    concurrente veía cero filas para ese work_order en vez de la vieja o la
    nueva.
    """
    fila = mapear_campos_clasicos(activity_json, dni_vendedor=dni_vendedor, fe_buscado=fe_buscado)
    fila.update(mapear_activity_a_columnas(activity_json))
    df = pd.DataFrame([fila], dtype=object)

    with engine_toa().begin() as conn:
        conn.execute(
            text("DELETE FROM fija_data_toa WHERE work_order = :fe"),
            {"fe": fe_buscado},
        )
        df.to_sql(name="fija_data_toa", con=conn, schema="dbo", if_exists="append", index=False)


def buscar_y_guardar(sesion: SesionTOA, fe: str, dni_vendedor: str = None) -> dict | None:
    """
    Busca un FE en TOA con la sesión ya autenticada, guarda el resultado en
    pbi2.fija_data_toa si lo encuentra. Devuelve el activity_json crudo, o
    None si TOA no tiene ese FE (petición válida pero nunca llegó a
    agendarse/registrarse ahí).
    """
    activity = buscar_y_extraer_fe(sesion, fe)
    if activity is None:
        return None
    _guardar_en_pbi2(activity, fe_buscado=fe, dni_vendedor=dni_vendedor)
    return activity


# ============================================================================
# Modo servicio: cola secuencial en memoria, sesión TOA persistente.
# Un solo hilo worker procesa las búsquedas una a la vez (mismo patrón
# anti-detección que ya usa scrapper.py) — evita ráfagas de requests
# simultáneas contra TOA aunque varios vendedores pregunten a la vez.
#
# QUEUE_MAXSIZE: sin límite, una ráfaga de consultas durante una lentitud de
# TOA hacía crecer la cola indefinidamente en vez de descartar carga. Con
# límite, put() bloquea si está llena — el llamador (el propio buscar())
# hereda ese bloqueo dentro de su timeout normal, así que no hace falta
# manejarlo aparte.
#
# resultado_slot["abandonado"]: cuando buscar() agota su timeout, marca el
# slot antes de retornar — si el worker todavía no llegó a ese job, lo salta
# sin gastar una búsqueda real en TOA (antes: el job abandonado igual se
# procesaba completo, aunque nadie fuera a leer la respuesta).
# ============================================================================

QUEUE_MAXSIZE = 20

# Si otro backoffice humano se loguea a TOA con la misma cuenta y marca
# "cerrar sesiones anteriores", nuestra sesión queda invalidada del lado
# del servidor sin que el proceso "muera" — sigue vivo según el sistema
# operativo, pero cualquier búsqueda empieza a fallar. Confirmado con el
# usuario (2026-08-21): esto pasa mientras varias personas comparten la
# misma cuenta TOA_PORTAL_USERNAME durante las pruebas. En vez de esperar
# a un vigilante externo (hasta varios minutos de downtime), el propio
# worker detecta N fallos consecutivos y dispara un re-login — el mismo
# login_y_obtener_sesion() ya marca "cerrar sesiones anteriores" (ver
# toa_client.py líneas 200-210), así que recupera el control de la cuenta.
FALLOS_CONSECUTIVOS_PARA_RELOGIN = 2

# Degradación silenciosa por sesión vieja (confirmado 2026-08-22): tras
# muchas horas de sesión continua (~19h reproducido en producción), la
# búsqueda de FEs NUEVOS empieza a devolver "no encontrado" de forma
# consistente y sospechosamente rápida (<0.3s, sin llegar a golpear TOA de
# verdad), mientras FEs ya vistos antes por esta misma sesión y una sesión
# Playwright recién logueada siguen funcionando bien — no es un error de
# conexión (no lanza excepción, por eso FALLOS_CONSECUTIVOS_PARA_RELOGIN
# nunca lo detecta) sino una respuesta "vacía pero válida" de TOA para esa
# sesión en particular. Mitigación: renovar la sesión por tiempo, no solo
# por fallos consecutivos.
RENOVACION_SESION_SEG = 4 * 60 * 60  # cada 4h, con margen generoso sobre las ~19h que sí fallaron


class ServicioBusquedaTOA:
    def __init__(self):
        self._sesion: SesionTOA | None = None
        self._sesion_lista = threading.Event()
        self._cola: Queue = Queue(maxsize=QUEUE_MAXSIZE)
        self._worker: threading.Thread | None = None
        self._fallos_consecutivos = 0
        self._sesion_creada_en = 0.0

    def iniciar(self):
        _log("Iniciando sesión TOA (login con Playwright)...")
        self._sesion = login_y_obtener_sesion()
        self._sesion_creada_en = time.time()
        self._sesion_lista.set()
        _log("Sesión obtenida. Servicio listo para atender búsquedas puntuales.")
        self._worker = threading.Thread(target=self._procesar_cola, daemon=True)
        self._worker.start()

    def iniciar_en_background(self):
        """
        Como iniciar(), pero no bloquea — corre el login en un hilo aparte.
        Permite levantar el servidor HTTP de inmediato (el socket queda
        escuchando desde el arranque) en vez de dejarlo sin bind durante
        los ~10-40s que puede tardar el login de Playwright; las requests
        que lleguen antes de que la sesión esté lista simplemente esperan
        en buscar() (ver _sesion_lista) en vez de recibir connection-refused.
        """
        threading.Thread(target=self.iniciar, daemon=True).start()

    def _relogin(self):
        """
        Re-login síncrono, bloqueando la cola mientras dura — ejecuta desde
        el propio hilo worker al detectar fallos consecutivos. login_y_obtener_sesion()
        marca "cerrar sesiones anteriores" (mismo código de siempre, ver
        toa_client.py), así que esto también nos recupera el control si un
        humano nos había desplazado.
        """
        _log("[ServicioBusquedaTOA] Fallos consecutivos detectados — re-login...")
        try:
            self._sesion = login_y_obtener_sesion()
            self._sesion_creada_en = time.time()
            self._fallos_consecutivos = 0
            _log("[ServicioBusquedaTOA] Re-login exitoso.")
        except Exception as e:
            _log(f"[ServicioBusquedaTOA] Re-login falló: {e} — se reintentará en el próximo fallo.")

    def _renovar_sesion_si_vieja(self):
        """
        Renovación proactiva por tiempo (ver RENOVACION_SESION_SEG) — la
        degradación de sesión vieja NO lanza excepción (TOA responde
        "no encontrado" limpiamente), así que FALLOS_CONSECUTIVOS_PARA_RELOGIN
        nunca la detecta. Se chequea antes de cada búsqueda en vez de con un
        timer aparte, para no competir por self._sesion con el propio worker.
        """
        edad = time.time() - self._sesion_creada_en
        if edad < RENOVACION_SESION_SEG:
            return
        _log(f"[ServicioBusquedaTOA] Sesión con {edad / 3600:.1f}h de antigüedad — renovando preventivamente...")
        try:
            self._sesion = login_y_obtener_sesion()
            self._sesion_creada_en = time.time()
            self._fallos_consecutivos = 0
            _log("[ServicioBusquedaTOA] Renovación preventiva exitosa.")
        except Exception as e:
            # No se actualiza _sesion_creada_en — se reintentará en la
            # próxima búsqueda en vez de esperar otras RENOVACION_SESION_SEG.
            _log(f"[ServicioBusquedaTOA] Renovación preventiva falló: {e} — se sigue usando la sesión actual.")

    def _procesar_cola(self):
        while True:
            fe, dni_vendedor, resultado_evento, resultado_slot = self._cola.get()
            if resultado_slot.get("abandonado"):
                self._cola.task_done()
                continue
            self._renovar_sesion_si_vieja()
            try:
                activity = buscar_y_guardar(self._sesion, fe, dni_vendedor=dni_vendedor)
                resultado_slot["activity"] = activity
                self._fallos_consecutivos = 0
                _log(f"[ServicioBusquedaTOA] {fe}: {'encontrado' if activity else 'no encontrado'} (estado={activity.get('astatus') if activity else None})")
            except Exception as e:
                resultado_slot["error"] = str(e)
                self._fallos_consecutivos += 1
                _log(f"[ServicioBusquedaTOA] Fallo #{self._fallos_consecutivos} buscando {fe}: {e}")
                if self._fallos_consecutivos >= FALLOS_CONSECUTIVOS_PARA_RELOGIN:
                    self._relogin()
            finally:
                resultado_evento.set()
                self._cola.task_done()

    def buscar(self, fe: str, dni_vendedor: str = None, timeout: float = 60.0) -> dict | None:
        """
        Encola una búsqueda y espera (bloqueante) hasta que se resuelve o se
        agota el timeout. Es la función que llamará consultar_estado_fe.py
        cuando el paso 3 no encuentre nada — el vendedor espera en silencio
        hasta tener el resultado final (decisión ya confirmada en el diseño).

        Si el servicio arrancó con iniciar_en_background() y el login de
        Playwright todavía no terminó, espera aquí (consumiendo parte del
        propio `timeout`) en vez de fallar de inmediato — así el servidor
        HTTP puede aceptar conexiones desde el arranque sin que las
        primeras requests reciban un error solo por timing.
        """
        if not self._sesion_lista.wait(timeout=timeout):
            raise RuntimeError("Servicio no terminó de iniciar sesión TOA a tiempo")

        resultado_evento = threading.Event()
        resultado_slot = {}
        self._cola.put((fe, dni_vendedor, resultado_evento, resultado_slot))

        if not resultado_evento.wait(timeout=timeout):
            resultado_slot["abandonado"] = True  # el worker lo saltará si aún no lo tomó
            return None  # timeout: se trata igual que "no se pudo verificar"

        if "error" in resultado_slot:
            raise RuntimeError(resultado_slot["error"])
        return resultado_slot.get("activity")


# ============================================================================
# Servidor HTTP — consumido por wa_toa_listener.js. Un solo endpoint
# síncrono: recibe el FE, bloquea hasta que ServicioBusquedaTOA lo resuelve
# (cola secuencial interna, ya con sesión TOA viva), responde con el
# resultado. Sin dependencias externas — http.server de la librería estándar.
# ============================================================================

class _HandlerBusqueda(BaseHTTPRequestHandler):
    servicio: ServicioBusquedaTOA = None  # se inyecta antes de arrancar el server

    def log_message(self, format, *args):
        pass  # el logging propio ya imprime lo relevante; silenciar el default de BaseHTTPRequestHandler

    def do_GET(self):
        if self.path == "/health":
            listo = self.servicio is not None and self.servicio._sesion_lista.is_set()
            self._responder(200, {"status": "ready" if listo else "iniciando"})
        else:
            self._responder(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/buscar":
            self._responder(404, {"error": "not found"})
            return

        largo = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            self._responder(400, {"error": "body invalido, se espera JSON"})
            return

        # json.loads() acepta cualquier JSON válido, no solo objetos — un
        # body malformado (ej. un string suelto) pasaría el parseo sin
        # error pero rompería body.get() más abajo. Guard defensivo: nunca
        # se reprodujo con certeza qué origina un body no-dict (visto una
        # vez en pruebas reales 2026-08-20 contra un proceso que llevaba
        # corriendo desde antes de varios reintentos fallidos de pbi2; no
        # se repitió tras reiniciar el proceso), pero es mejor un 400 claro
        # que un 500 con AttributeError.
        if not isinstance(body, dict):
            self._responder(400, {"error": f"body debe ser un objeto JSON, se recibió {type(body).__name__}"})
            return

        fe = (body.get("fe") or "").strip().upper()
        if not fe:
            self._responder(400, {"error": "campo 'fe' requerido"})
            return

        dni_vendedor = body.get("dni_vendedor")
        inicio = time.time()
        try:
            activity = self.servicio.buscar(fe, dni_vendedor=dni_vendedor)
        except Exception as e:
            self._responder(500, {"error": str(e)})
            return
        duracion = time.time() - inicio

        if activity is None:
            self._responder(200, {"encontrado": False, "fe": fe, "duracion_seg": round(duracion, 1)})
        else:
            self._responder(200, {
                "encontrado": True,
                "fe": fe,
                "estado": activity.get("astatus"),
                "duracion_seg": round(duracion, 1),
            })

    def _responder(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _vigilar_cierre_ventana(server: ThreadingHTTPServer):
    """
    Defensa en profundidad: el Task Scheduler es quien debería detener este
    proceso a las 20:00 (ver VENTANA_FIN), pero si por lo que sea no lo hace
    a tiempo, este hilo cierra el servidor igual — nunca debe quedar una
    sesión TOA autenticada corriendo fuera de la ventana laboral.
    """
    while True:
        time.sleep(60)
        if not _dentro_de_ventana_laboral():
            _log("Fin de ventana laboral (20:00) — cerrando servidor y sesión TOA.")
            threading.Thread(target=server.shutdown, daemon=True).start()
            return


def _correr_servidor_http():
    if not _dentro_de_ventana_laboral():
        _log(
            f"Fuera de ventana laboral ({VENTANA_INICIO}-{VENTANA_FIN}) — "
            "el servicio de búsqueda TOA no debe operar 24/7 (riesgo frente a "
            "Seguridad de Telefónica). No se inicia sesión. Saliendo."
        )
        sys.exit(0)

    servicio = ServicioBusquedaTOA()
    _HandlerBusqueda.servicio = servicio

    # El socket se liga ANTES del login (que puede tardar decenas de
    # segundos y hasta 3 reintentos) — antes, una request/health-check
    # durante el arranque recibía connection-refused en vez de una espera
    # válida. buscar() ya sabe esperar a que la sesión esté lista.
    server = ThreadingHTTPServer(("localhost", HTTP_PORT), _HandlerBusqueda)
    _log(f"Servidor HTTP escuchando en puerto {HTTP_PORT} — POST /buscar {{'fe': 'FE-...'}}")

    servicio.iniciar_en_background()
    threading.Thread(target=_vigilar_cierre_ventana, args=(server,), daemon=True).start()
    server.serve_forever()


def main():
    if "--http" in sys.argv:
        _correr_servidor_http()
        return

    if "--serve" in sys.argv:
        servicio = ServicioBusquedaTOA()
        servicio.iniciar()
        print("Escribe un FE por línea (o 'salir' para terminar):")
        for linea in sys.stdin:
            fe = linea.strip()
            if not fe or fe.lower() == "salir":
                break
            inicio = time.time()
            activity = servicio.buscar(fe)
            duracion = time.time() - inicio
            if activity:
                print(f"  {fe}: encontrado (estado={activity.get('astatus')}) en {duracion:.1f}s")
            else:
                print(f"  {fe}: no encontrado en TOA ({duracion:.1f}s)")
        return

    if len(sys.argv) < 2:
        print("Uso: python toa_servicio_busqueda.py FE-XXXXXXXXXX")
        print("     python toa_servicio_busqueda.py --serve")
        sys.exit(1)

    fe = sys.argv[1]
    print("Login puntual (más lento que --serve, solo para pruebas)...")
    sesion = login_y_obtener_sesion()
    activity = buscar_y_guardar(sesion, fe)
    if activity:
        print(f"{fe}: encontrado y guardado en pbi2.fija_data_toa (estado={activity.get('astatus')})")
    else:
        print(f"{fe}: no encontrado en TOA")


if __name__ == "__main__":
    main()

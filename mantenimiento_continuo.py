"""
Mantenimiento continuo de pbi2.fija_data_toa — "fase 2" del diseño original
de arquitectura (búsqueda activa de FEs nuevos de VENTORY + re-verificación
de transitorios), reconstruido desde cero (2026-08-21) sobre las piezas que
sí funcionan hoy: ServicioBusquedaTOA (sesión TOA persistente, cola
secuencial, deduplicación) y el caché local (cache_toa.py).

No reutiliza la tarea programada vieja "Toa BOT" (deshabilitada, apuntaba
a una copia de scrapper.py de agosto 2025 — Selenium puro, sin
config.py centralizado, sin cliente híbrido, sin las 137 columnas nuevas).
Este script es una reconstrucción con el mismo objetivo, no una migración
de aquel código.

Dos responsabilidades en un solo proceso (comparten la misma sesión TOA,
evita dos procesos compitiendo por login/cola):

1. FEs NUEVOS: peticiones activas del mes actual en eAuren (ver
   scripts_db/peticiones_activas_mes.py) que aún no están en el caché
   local — nunca se buscaron en TOA. Se buscan y se guardan en pbi2.

2. TRANSITORIOS A RE-VERIFICAR: FEs que YA están en el caché con estado
   Iniciado/Pendiente/Enviado/Suspendido (no definitivo) y cuyo dato
   cacheado tiene más de UMBRAL_REVERIFICACION_MIN minutos — se vuelven a
   buscar en TOA por si cambiaron de estado (ej. pasaron a Completado o
   Cancelado).

Al final de cada corrida, dispara un refresco del caché local
(refrescar_cache_toa.py) para que los cambios se reflejen de inmediato en
vez de esperar el próximo ciclo de RefrescarCacheTOA.

Pensado para tarea programada de Windows cada 15 min (mismo patrón que
resucitar_yugi.ps1 / RefrescarCacheTOA).

Uso:
    python mantenimiento_continuo.py
"""
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from cache_toa import DB_PATH as CACHE_DB_PATH
from config import engine_ventory_pg
from scripts_db.peticiones_activas_mes import obtener_peticiones_activas_mes
from toa_servicio_busqueda import (
    VENTANA_FIN,
    VENTANA_INICIO,
    ServicioBusquedaTOA,
    _dentro_de_ventana_laboral,
)

ESTADOS_TRANSITORIOS = ("Iniciado", "Pendiente", "Enviado", "Suspendido")
UMBRAL_REVERIFICACION_MIN = 20
PYTHON_EXE = sys.executable

# La tarea programada de Windows no captura stdout a ningún archivo por
# defecto — sin este log persistente, una corrida automática que falla o
# se comporta raro es indetectable hasta que alguien nota un dato faltante
# (confirmado 2026-08-21: la primera corrida automática de
# MantenimientoContinuoTOA no dejó ningún rastro verificable más allá de
# inferir por el timestamp del refresco del caché). print() se mantiene
# para cuando se corre manualmente en una terminal.
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "mantenimiento_continuo.log"


def _log(mensaje: str) -> None:
    print(mensaje)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {mensaje}\n")


def _resolver_fes_activos_mes_actual() -> pd.DataFrame:
    """Peticiones activas del mes actual (eAuren) resueltas a FE (VENTORY)."""
    hoy = date.today()
    df_peticiones = obtener_peticiones_activas_mes(hoy.year, hoy.month)

    peticiones = df_peticiones["peticion"].dropna().astype(str).tolist()
    if not peticiones:
        return pd.DataFrame(columns=["fe", "peticion"])

    placeholders = ",".join(f"'{p}'" for p in peticiones)
    query = f"""
        SELECT codigo_seguridad AS fe, codigo_seguridad_2 AS peticion
        FROM ventas
        WHERE codigo_seguridad_2 IN ({placeholders})
    """
    return pd.read_sql(query, engine_ventory_pg())


def _fes_ya_en_cache() -> set[str]:
    """work_order ya presentes en el caché local — evita re-buscar en TOA
    lo que ya se tiene, sin tocar pbi2 para esta comprobación."""
    if not CACHE_DB_PATH.exists():
        return set()
    import sqlite3

    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        cur = conn.execute("SELECT work_order FROM fija_data_toa_cache")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _fes_transitorios_a_reverificar() -> list[str]:
    """
    work_order en el caché con estado no definitivo y cuyo
    fecha_actualizacion tiene más de UMBRAL_REVERIFICACION_MIN minutos —
    candidatos a haber cambiado de estado en TOA desde la última vez que
    se buscaron.
    """
    if not CACHE_DB_PATH.exists():
        return []
    import sqlite3

    limite = datetime.now() - timedelta(minutes=UMBRAL_REVERIFICACION_MIN)
    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        placeholders = ",".join("?" for _ in ESTADOS_TRANSITORIOS)
        cur = conn.execute(
            f"""
            SELECT work_order, fecha_actualizacion FROM fija_data_toa_cache
            WHERE estado_general IN ({placeholders})
            """,
            ESTADOS_TRANSITORIOS,
        )
        candidatos = []
        for work_order, fecha_str in cur.fetchall():
            try:
                fecha = datetime.fromisoformat(fecha_str)
            except (TypeError, ValueError):
                candidatos.append(work_order)  # fecha ilegible: mejor re-verificar
                continue
            if fecha < limite:
                candidatos.append(work_order)
        return candidatos
    finally:
        conn.close()


def _procesar_lista(servicio: ServicioBusquedaTOA, fes: list[str], etiqueta: str) -> dict:
    total = len(fes)
    _log(f"=== {etiqueta}: {total} FEs ===")
    encontrados = no_encontrados = errores = 0
    for idx, fe in enumerate(fes, start=1):
        inicio = time.time()
        try:
            activity = servicio.buscar(fe)
            duracion = time.time() - inicio
            if activity is not None:
                encontrados += 1
                _log(f"[{idx}/{total}] {fe}: OK (estado={activity.get('astatus')}, {duracion:.1f}s)")
            else:
                no_encontrados += 1
                _log(f"[{idx}/{total}] {fe}: no encontrado en TOA ({duracion:.1f}s)")
        except Exception as e:
            errores += 1
            _log(f"[{idx}/{total}] {fe}: ERROR - {e}")
    return {"encontrados": encontrados, "no_encontrados": no_encontrados, "errores": errores}


def main():
    # Este proceso hace login TOA (vía ServicioBusquedaTOA) igual que
    # toa_servicio_busqueda.py --http — mismo riesgo de huella de actividad
    # fuera de horario laboral frente a Seguridad de Telefónica (confirmado
    # con el usuario 2026-08-24). Restringido a la misma ventana 8:00-20:00.
    if not _dentro_de_ventana_laboral():
        _log(f"Fuera de ventana laboral ({VENTANA_INICIO}-{VENTANA_FIN}) — ciclo omitido, sin login TOA.")
        return

    _log("=== Inicio de ciclo ===")
    _log("Resolviendo peticiones activas del mes actual (eAuren -> VENTORY)...")
    df_fes_activos = _resolver_fes_activos_mes_actual()
    fes_activos = set(df_fes_activos["fe"].dropna().tolist())
    _log(f"Peticiones activas resueltas a FE: {len(fes_activos)}")

    en_cache = _fes_ya_en_cache()
    fes_nuevos = sorted(fes_activos - en_cache)
    _log(f"De esos, ya en caché: {len(fes_activos & en_cache)} - nuevos a buscar: {len(fes_nuevos)}")

    fes_reverificar = sorted(set(_fes_transitorios_a_reverificar()) & fes_activos)
    _log(f"Transitorios a re-verificar (cache > {UMBRAL_REVERIFICACION_MIN} min): {len(fes_reverificar)}")

    if not fes_nuevos and not fes_reverificar:
        _log("Nada que procesar en este ciclo.")
        return

    _log("Iniciando sesión TOA (login con Playwright)...")
    try:
        servicio = ServicioBusquedaTOA()
        servicio.iniciar()
    except Exception as e:
        _log(f"[ERROR] No se pudo iniciar sesión TOA - ciclo abortado: {e}")
        return
    _log("Sesión obtenida.")

    resumen_nuevos = _procesar_lista(servicio, fes_nuevos, "FEs nuevos") if fes_nuevos else {}
    resumen_reverif = (
        _procesar_lista(servicio, fes_reverificar, "Re-verificación de transitorios")
        if fes_reverificar
        else {}
    )

    _log("=== Resumen del ciclo ===")
    if resumen_nuevos:
        _log(f"Nuevos: {resumen_nuevos}")
    if resumen_reverif:
        _log(f"Re-verificados: {resumen_reverif}")

    _log("Refrescando caché local...")
    try:
        subprocess.run(
            [PYTHON_EXE, str(Path(__file__).parent / "refrescar_cache_toa.py")],
            check=True,
            timeout=60,
        )
        _log("Caché refrescado correctamente.")
    except Exception as e:
        _log(f"[WARN] No se pudo refrescar el caché al final del ciclo: {e}")

    _log("=== Fin de ciclo ===")


if __name__ == "__main__":
    main()

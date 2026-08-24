"""
Caché local (SQLite) de pbi2.fija_data_toa — resuelve la dependencia de una
consulta EN VIVO a SQL Server en el camino crítico de respuesta del bot de
WhatsApp. pbi2 (usuario adminpbi2) tiene fallos intermitentes de conexión
(SQL Server 18456) confirmados en producción (2026-08-20/21) — cada vez que
esto ocurre justo cuando un vendedor pregunta /estado, el bot no puede
responder con un dato que, la mayor parte del tiempo, ya conoce.

Diseño: un proceso aparte (refrescar_cache_toa.py, vía tarea programada
cada 5-10 min) relee pbi2.fija_data_toa completa a este SQLite local. El
bot (consultar_estado_fe.py) SIEMPRE lee de aquí para el paso 3 — nunca
toca pbi2 en el camino de respuesta al vendedor. Si pbi2 está caída en el
momento exacto de una consulta, el bot igual responde con el último dato
bueno cacheado (a lo sumo unos minutos desactualizado) en vez de fallar.

El refresco en sí SÍ toca pbi2 — pero solo una vez cada varios minutos,
en un proceso separado del camino de respuesta, así que un fallo puntual
del refresco no afecta a ningún vendedor esperando una respuesta.

Uso:
    from cache_toa import obtener_fila_cache, cache_desactualizado

    fila = obtener_fila_cache("FE-1128653298")   # o None si no está cacheado
    if cache_desactualizado(minutos_maximo=15):
        ...  # avisar/loguear que el refresco lleva rato sin correr
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "cache_toa.db"

COLUMNAS = [
    "work_order",
    "estado_general",
    "fecha_agendamiento",
    "franja_agendamiento",
    "intervalo_tiempo",
    "motivo_no_realizado_instalacion",
    "fecha_actualizacion",
]


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_esquema() -> None:
    """Crea la tabla y metadatos si no existen. Idempotente."""
    with _conectar() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fija_data_toa_cache (
                work_order TEXT PRIMARY KEY,
                estado_general TEXT,
                fecha_agendamiento TEXT,
                franja_agendamiento TEXT,
                intervalo_tiempo TEXT,
                motivo_no_realizado_instalacion TEXT,
                fecha_actualizacion TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_metadata (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )


def reemplazar_cache_completo(filas: list[dict]) -> int:
    """
    Reemplaza el contenido completo de la tabla cacheada por `filas` —
    atómico (una sola transacción: DELETE + INSERT masivo), así una
    consulta concurrente durante el refresco nunca ve una tabla a medio
    vaciar. Devuelve la cantidad de filas insertadas.

    Se usa reemplazo completo (no upsert incremental) porque el volumen es
    chico (miles de filas, no millones) y así un FE que pasó a un estado
    que ya no cumple el filtro de refresco (ver refrescar_cache_toa.py)
    desaparece limpiamente del caché en vez de quedar con datos viejos.
    """
    inicializar_esquema()
    with _conectar() as conn:
        conn.execute("DELETE FROM fija_data_toa_cache")
        # pbi2.fija_data_toa puede tener work_order duplicados (historial
        # acumulado del scraper Selenium original, antes de la
        # deduplicación agregada en toa_servicio_busqueda.py) — INSERT OR
        # REPLACE en vez de INSERT: al venir `filas` ordenado por
        # fecha_actualizacion ascendente (ver refrescar_cache_toa.py), la
        # última inserción de cada work_order es la más reciente y prevalece.
        conn.executemany(
            f"""
            INSERT OR REPLACE INTO fija_data_toa_cache ({", ".join(COLUMNAS)})
            VALUES ({", ".join("?" for _ in COLUMNAS)})
            """,
            [tuple(fila.get(c) for c in COLUMNAS) for fila in filas],
        )
        conn.execute(
            "INSERT OR REPLACE INTO cache_metadata (clave, valor) VALUES ('ultimo_refresco', ?)",
            (datetime.now().isoformat(),),
        )
        return len(filas)


def obtener_fila_cache(work_order: str) -> sqlite3.Row | None:
    """Lee una fila del caché local — nunca toca pbi2."""
    inicializar_esquema()
    with _conectar() as conn:
        cur = conn.execute(
            "SELECT * FROM fija_data_toa_cache WHERE work_order = ?", (work_order,)
        )
        return cur.fetchone()


def ultimo_refresco() -> datetime | None:
    inicializar_esquema()
    with _conectar() as conn:
        cur = conn.execute("SELECT valor FROM cache_metadata WHERE clave = 'ultimo_refresco'")
        fila = cur.fetchone()
        if fila is None:
            return None
        return datetime.fromisoformat(fila["valor"])


def cache_desactualizado(minutos_maximo: int = 20) -> bool:
    """
    True si el caché nunca se refrescó, o si el último refresco fue hace
    más de `minutos_maximo` — señal de que el proceso de refresco periódico
    dejó de correr (ej. la tarea programada falló silenciosamente), no de
    que el dato individual de un FE esté desactualizado.
    """
    ultimo = ultimo_refresco()
    if ultimo is None:
        return True
    return datetime.now() - ultimo > timedelta(minutes=minutos_maximo)

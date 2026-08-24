"""
Refresca cache_toa.db (SQLite local) desde pbi2.fija_data_toa. Pensado
para correr periódicamente vía tarea programada de Windows (cada 5-10 min,
mismo patrón que resucitar_yugi.ps1) — separado del camino de respuesta
del bot, así un fallo de conexión aquí solo retrasa el refresco, nunca
bloquea a un vendedor esperando /estado.

Alcance del SELECT: SOLO mes actual (confirmado con el usuario: no hace
falta cachear el histórico completo de 29,552 filas acumuladas por
scrapper.py desde hace meses — con el mes actual alcanza y sobra, del
orden de unos pocos miles de registros como mucho). Filtra por
fecha_actualizacion >= inicio del mes actual — columna DATETIME real en
SQL Server (confirmado vía INFORMATION_SCHEMA, no NVARCHAR mixto como
fecha_agendamiento), así el filtro de fecha es confiable del lado del
servidor.

Uso:
    python refrescar_cache_toa.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from config import engine_toa
from cache_toa import reemplazar_cache_completo

QUERY = """
    SELECT work_order, estado_general, fecha_agendamiento, franja_agendamiento,
           intervalo_tiempo, motivo_no_realizado_instalacion, fecha_actualizacion
    FROM fija_data_toa
    WHERE work_order LIKE 'FE-%'
      AND fecha_actualizacion >= ?
"""


def main():
    inicio_mes = date.today().replace(day=1)
    print(f"Leyendo pbi2.fija_data_toa (fecha_actualizacion >= {inicio_mes})...")
    df = pd.read_sql(QUERY, engine_toa(), params=(inicio_mes,))
    print(f"Filas leídas: {len(df)}")

    # sqlite3 no serializa pandas.Timestamp/NaT directamente — convertir a
    # Ordenar por fecha_actualizacion (aún datetime64 real) ANTES de
    # convertir a string — necesario porque reemplazar_cache_completo()
    # usa INSERT OR REPLACE para resolver work_order duplicados (ver
    # cache_toa.py): la última fila de cada work_order en `filas` es la
    # que prevalece, así que debe quedar ordenado de más vieja a más nueva.
    df = df.sort_values("fecha_actualizacion", na_position="first")

    # sqlite3 no serializa pandas.Timestamp/NaT directamente — convertir a
    # string (o None) después de ordenar. fecha_agendamiento/
    # franja_agendamiento son NVARCHAR de origen (no datetime), así que
    # solo fecha_actualizacion necesita esta conversión.
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].astype(str)
    df = df.where(pd.notna(df), None)

    filas = df.to_dict(orient="records")
    total = reemplazar_cache_completo(filas)
    print(f"Caché local actualizado: {total} filas.")


if __name__ == "__main__":
    main()

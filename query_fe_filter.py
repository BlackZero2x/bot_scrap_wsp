# Conexión a la base de datos
from sqlalchemy import text
import pandas as pd
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

# Importar configuración centralizada
sys.path.insert(0, str(Path(__file__).parent))
from config import engine_toa, engine_ventory_pg
from scripts_db.peticiones_activas_mes import obtener_peticiones_activas_mes

engine_toa = engine_toa()

# Ventana de corte: mismo criterio que la versión anterior a la migración a
# VENTORY (fija_controlnet_detallado, ver historial de este archivo) — sin
# esto, un FE de VENTORY con cero filas en fija_data_toa (saltado en una
# corrida previa, o entrada vieja del sheet) nunca se excluye del filtro
# NOT IN de abajo y se re-scrapea en cada corrida del bot indefinidamente.
MESES_ANTIGUEDAD_MAXIMA = 2


def _resolver_fes_ventory(fecha_corte: datetime) -> pd.DataFrame:
    """
    Peticiones activas en eAuren (mes actual y anterior, según
    MESES_ANTIGUEDAD_MAXIMA) resueltas a FE vía VENTORY Postgres
    (ventas_db.ventas: codigo_seguridad = FE, codigo_seguridad_2 = peticion —
    puente confirmado, ver config.py). Reemplaza al Google Sheet
    REG_VTAS_BBDD (migración 2026-08), que dejó de ser la fuente de FEs.
    """
    hoy = datetime.now()
    meses = {(hoy.year, hoy.month)}
    cursor = hoy
    while datetime(cursor.year, cursor.month, 1) >= fecha_corte.replace(day=1):
        cursor = cursor - relativedelta(months=1)
        meses.add((cursor.year, cursor.month))

    frames = [obtener_peticiones_activas_mes(anio, mes) for anio, mes in meses]
    df_peticiones = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df_peticiones.empty:
        return pd.DataFrame(columns=["codigo_fe", "dni_vendedor", "fecha_registro"])

    peticiones = df_peticiones["peticion"].dropna().astype(str).unique().tolist()
    if not peticiones:
        return pd.DataFrame(columns=["codigo_fe", "dni_vendedor", "fecha_registro"])

    placeholders = ",".join(f"'{p}'" for p in peticiones)
    query = f"""
        SELECT codigo_seguridad AS codigo_fe, codigo_seguridad_2 AS peticion
        FROM ventas
        WHERE codigo_seguridad_2 IN ({placeholders})
    """
    df_ventory = pd.read_sql(query, engine_ventory_pg())

    # dni_vendedor viene de eAuren (documento_vendedor), no de la tabla
    # ventas de Postgres — esta no tiene esa columna.
    df = df_ventory.merge(
        df_peticiones[["peticion", "fecha_registro", "documento_vendedor"]],
        on="peticion",
        how="left",
    ).rename(columns={"documento_vendedor": "dni_vendedor"})
    return df[["codigo_fe", "dni_vendedor", "fecha_registro"]]


def filter_query():
    """
    Fuente de FEs pendientes: VENTORY (Postgres ventas_db, vía eAuren para
    peticiones activas del mes). Se excluyen los FEs cuyo estado_general en
    pbi2.fija_data_toa ya está en un estado final, y los que tengan
    fecha_registro más antigua que MESES_ANTIGUEDAD_MAXIMA.

    Returns:
        list: lista de [codigo_fe, dni_vendedor] pendientes de procesar
    """
    fecha_corte = datetime.now() - relativedelta(months=MESES_ANTIGUEDAD_MAXIMA)
    df1 = _resolver_fes_ventory(fecha_corte)

    df1["fecha_registro"] = pd.to_datetime(df1["fecha_registro"], errors="coerce")
    df1 = df1[df1["fecha_registro"] >= fecha_corte]

    df1 = df1[["codigo_fe", "dni_vendedor"]]

    query3 = """SELECT work_order
                FROM fija_data_toa
                WHERE estado_general  NOT IN ('No Realizada', 'Iniciado', 'Pendiente', 'Suspendido');"""
    df3 = pd.read_sql(query3, engine_toa)

    work_orders_en_df3 = df3["work_order"]
    df1_filtrado = df1[~df1["codigo_fe"].isin(work_orders_en_df3)]
    lista = df1_filtrado.values.tolist()
    return lista


if __name__ == "__main__":
    print(filter_query())
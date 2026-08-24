"""
Explora peticiones "activas" del mes en eAuren.dbo.fija_registros_totales,
enriquecidas con eAuren.dbo.fija_altas — NO forma parte todavía del flujo
productivo de query_fe_filter.py (que hoy sigue usando VENTORY como única
fuente de candidatos). Script standalone para seguir validando el criterio
antes de decidir cómo/si se integra.

Criterio (confirmado con el usuario):
- Una petición pertenece al "mes de corte" si su fecha_registro cae en ese
  mes, O si su fecha_alta (en fija_altas) cae en ese mes — cubre ventas de
  fin de mes cuya alta se registra el mes siguiente.
- Se excluye si fija_registros_totales.desc_estado_peticion ya es
  'Cancelado' o 'Cerrado' (venta resuelta).
- Se excluye también si fija_altas.desc_estado_peticion es 'Cerrado', aun
  cuando fija_registros_totales no se haya actualizado — es un caso real
  observado (peticion 1810898514: registro dice "Enviado" pero el alta ya
  está Cerrada).
- Esto NO reemplaza el filtro final contra pbi2.fija_data_toa.estado_general
  que ya hace query_fe_filter.py — una vez que TOA confirma Cerrado/
  Completado para un FE, esa es la fuente de verdad para no re-buscarlo.

Uso:
    python scripts_db/peticiones_activas_mes.py [YYYY-MM]
    (sin argumento, usa el mes actual)
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import engine_auren

QUERY = """
SELECT
    rt.peticion,
    rt.desc_estado_peticion AS estado_registro,
    rt.fecha_registro,
    fa.fecha_alta,
    fa.desc_estado_peticion AS estado_alta,
    rt.cod_vendedor,
    rt.vendedor,
    rt.documento_vendedor
FROM dbo.fija_registros_totales rt
LEFT JOIN dbo.fija_altas fa
    ON rt.peticion = fa.peticion
WHERE
    (
        (rt.fecha_registro >= ? AND rt.fecha_registro < ?)
        OR (fa.fecha_alta >= ? AND fa.fecha_alta < ?)
    )
    AND (rt.desc_estado_peticion IS NULL OR rt.desc_estado_peticion NOT IN ('Cancelado', 'Cerrado'))
    AND (fa.desc_estado_peticion IS NULL OR fa.desc_estado_peticion <> 'Cerrado')
ORDER BY rt.fecha_registro DESC
"""


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return inicio, fin


def obtener_peticiones_activas_mes(anio: int, mes: int) -> pd.DataFrame:
    inicio, fin = _rango_mes(anio, mes)
    return pd.read_sql(
        QUERY, engine_auren(), params=(inicio, fin, inicio, fin)
    )


def main():
    if len(sys.argv) > 1:
        anio, mes = map(int, sys.argv[1].split("-"))
    else:
        hoy = date.today()
        anio, mes = hoy.year, hoy.month

    df = obtener_peticiones_activas_mes(anio, mes)
    print(f"Peticiones activas para {anio}-{mes:02d}: {len(df)}")
    if not df.empty:
        print(df["estado_registro"].value_counts(dropna=False))
        print()
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()

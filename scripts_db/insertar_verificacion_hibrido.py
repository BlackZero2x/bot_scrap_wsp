"""
Inserta a pbi2.dbo.fija_data_toa los resultados ya obtenidos en
verificacion_hibrido_resultado.json (17 FEs, capturados por toa_client.py
en la verificación de la migración híbrida).

Combina, por cada FE encontrado:
- Campos clásicos (~35, columnas ya existentes) vía
  scripts_db/campos_clasicos_mapper.py
- Columnas nuevas (137, prefijo toa_) ya calculadas en
  verificacion_hibrido_resultado.json (columnas_nuevas_mapeadas)

No vuelve a llamar a TOA — usa los datos ya capturados. dni_vendedor queda
NULL porque estos FEs de prueba no vienen de VENTORY (no hay vendedor
asociado conocido en este contexto).

Uso:
    python scripts_db/insertar_verificacion_hibrido.py [--dry-run]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config import engine_toa
from scripts_db.campos_clasicos_mapper import mapear_campos_clasicos

RUTA_RESULTADO = Path(__file__).parent.parent / "verificacion_hibrido_resultado.json"


def construir_filas():
    with open(RUTA_RESULTADO, encoding="utf-8") as f:
        data = json.load(f)

    filas = []
    for fe, v in data.items():
        if not v.get("encontrado") or not v.get("activity"):
            continue
        act = v["activity"]
        fila = mapear_campos_clasicos(act, dni_vendedor=None, fe_buscado=fe)
        fila.update(v.get("columnas_nuevas_mapeadas", {}))
        filas.append(fila)

    return filas


def main():
    dry_run = "--dry-run" in sys.argv

    filas = construir_filas()
    print(f"Filas a insertar: {len(filas)}")
    if not filas:
        print("Nada que insertar.")
        return

    # Cada fila trae un subconjunto distinto de las 137 columnas nuevas
    # (según qué formularios aplicaron a ese FE) — pd.DataFrame rellena las
    # celdas ausentes con NaN (float) sin importar el dtype solicitado, y
    # además puede recastear columnas con mayoría de None a float64,
    # normalizando None -> NaN también ahí. pyodbc no sabe convertir
    # float('nan') a NULL en columnas NVARCHAR, así que se completa
    # explícitamente cada fila con None antes de crear el DataFrame.
    todas_las_columnas = sorted({k for fila in filas for k in fila.keys()})
    filas_completas = [
        {col: fila.get(col) for col in todas_las_columnas}
        for fila in filas
    ]
    df = pd.DataFrame(filas_completas, columns=todas_las_columnas, dtype=object)
    print(f"Columnas por fila: {len(df.columns)}")
    print(f"work_order de la muestra: {df['work_order'].tolist()}")

    if dry_run:
        print("\n--dry-run: no se inserta nada. Vista previa de la primera fila:")
        print(df.iloc[0].to_dict())
        return

    exitosas = 0
    for idx, fila in df.iterrows():
        fila_df = pd.DataFrame([fila])
        try:
            fila_df.to_sql(
                name="fija_data_toa",
                con=engine_toa(),
                schema="dbo",
                if_exists="append",
                index=False,
            )
            exitosas += 1
        except Exception as e:
            print(f"  [ERROR] fila {idx} (work_order={fila.get('work_order')}): {e}")

    print(f"\n{exitosas}/{len(df)} filas insertadas en pbi2.dbo.fija_data_toa")


if __name__ == "__main__":
    main()

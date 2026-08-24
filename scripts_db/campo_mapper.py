"""
Mapea el JSON de actividad de TOA (delta.Activity[aid], obtenido vía
toa_client.py) a las 137 columnas nuevas ya creadas en pbi2.dbo.fija_data_toa
(ver alter_fija_data_toa.sql, ya ejecutado).

Usa columnas_nuevas_propuestas.json (raíz del proyecto) como fuente de
verdad del mapeo key_json -> nombre de columna SQL. Es aditivo: no toca los
~35 campos "clásicos" que ya usa scrapper.py (dict_info_cod), solo agrega
las columnas nuevas cuando el valor está presente en el JSON de la actividad.
"""
import json
from pathlib import Path

_RUTA_COLUMNAS = Path(__file__).parent.parent / "columnas_nuevas_propuestas.json"

_columnas_nuevas = None


def _cargar_columnas_nuevas():
    global _columnas_nuevas
    if _columnas_nuevas is None:
        with open(_RUTA_COLUMNAS, encoding="utf-8") as f:
            _columnas_nuevas = json.load(f)
    return _columnas_nuevas


def mapear_activity_a_columnas(activity_json: dict) -> dict:
    """
    Recibe el dict de una actividad (delta.Activity[aid] tal cual lo
    devuelve TOA) y devuelve {nombre_columna_sql: valor} solo para los
    campos presentes en columnas_nuevas_propuestas.json que además
    aparezcan en activity_json con un valor no vacío.
    """
    columnas = _cargar_columnas_nuevas()
    resultado = {}

    for col in columnas:
        key = col["key_json"]
        if key in activity_json:
            valor = activity_json[key]
            if valor not in (None, ""):
                resultado[col["columna"]] = valor

    return resultado


if __name__ == "__main__":
    columnas = _cargar_columnas_nuevas()
    print(f"Total columnas mapeables: {len(columnas)}")

    # Prueba rápida con un dict de ejemplo
    ejemplo = {"1014": "SI", "appt_number": "FE-1129056718", "campo_inexistente": "x"}
    print(mapear_activity_a_columnas(ejemplo))

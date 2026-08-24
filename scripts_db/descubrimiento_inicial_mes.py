"""
Descubrimiento inicial: busca en TOA todas las peticiones activas del mes
actual (eAuren, ya excluyendo Cancelado/Cerrado vía
scripts_db/peticiones_activas_mes.py) y las guarda en pbi2.fija_data_toa.

Contexto (sesión 2026-08-20): el bot de WhatsApp depende de que
pbi2.fija_data_toa ya tenga el dato cacheado para responder rápido — sin
esto, cada consulta de un vendedor cae en el paso 3b (búsqueda puntual bajo
demanda), lo cual es lento y genera carga innecesaria sobre TOA/pbi2 para
FEs que perfectamente podrían buscarse una sola vez, por adelantado.

Confirmado con datos reales antes de correr esto: de 2,623 FEs de VENTORY
del mes actual+anterior, solo 8 tenían fila en pbi2 (los tocados en
pruebas manuales) — el descubrimiento inicial nunca se había ejecutado.

Alcance (confirmado con el usuario, no el criterio amplio de antes):
- Solo mes ACTUAL (no mes anterior).
- Solo peticiones activas en eAuren (LEFT JOIN fija_altas, excluye
  Cancelado/Cerrado en ambas tablas) — ver peticiones_activas_mes.py.
- Solo las que se pueden resolver a FE vía VENTORY Postgres
  (codigo_seguridad_2 = peticion).

Reutiliza ServicioBusquedaTOA directamente en Python (mismo motor que usa
el servidor HTTP del puerto 8004, sin necesidad de levantar ese servidor
para esto) — un solo login, cola secuencial, mismo mapeo/guardado con
deduplicación ya usado por el paso 3b del bot.

Uso:
    python scripts_db/descubrimiento_inicial_mes.py
"""
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from config import engine_ventory_pg
from scripts_db.peticiones_activas_mes import obtener_peticiones_activas_mes
from toa_servicio_busqueda import ServicioBusquedaTOA


def _resolver_fes_del_mes_actual() -> pd.DataFrame:
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


def main():
    print("Resolviendo peticiones activas del mes actual (eAuren) a FE (VENTORY)...")
    df_fes = _resolver_fes_del_mes_actual()
    total = len(df_fes)
    print(f"Total de FEs a buscar en TOA: {total}")
    if total == 0:
        print("Nada que procesar.")
        return

    print("Iniciando sesión TOA (login con Playwright)...")
    servicio = ServicioBusquedaTOA()
    servicio.iniciar()
    print("Sesión obtenida. Procesando cola...\n")

    encontrados = 0
    no_encontrados = 0
    errores = 0

    for idx, fila in df_fes.iterrows():
        fe = fila["fe"]
        inicio = time.time()
        try:
            activity = servicio.buscar(fe)
            duracion = time.time() - inicio
            if activity is not None:
                encontrados += 1
                print(f"[{idx + 1}/{total}] {fe}: OK (estado={activity.get('astatus')}, {duracion:.1f}s)")
            else:
                no_encontrados += 1
                print(f"[{idx + 1}/{total}] {fe}: no encontrado en TOA ({duracion:.1f}s)")
        except Exception as e:
            errores += 1
            print(f"[{idx + 1}/{total}] {fe}: ERROR — {e}")

    print(f"\nResumen: {encontrados} encontrados, {no_encontrados} no encontrados en TOA, {errores} errores")
    print(f"Total procesados: {encontrados + no_encontrados + errores}/{total}")


if __name__ == "__main__":
    main()

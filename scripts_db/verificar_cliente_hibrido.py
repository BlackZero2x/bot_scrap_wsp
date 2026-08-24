"""
Verificación standalone del cliente híbrido (toa_client.py + campo_mapper.py)
contra una lista de FEs reales, sin tocar SQL Server ni el flujo productivo
de scrapper.py::start_bot().

Uso:
    python scripts_db/verificar_cliente_hibrido.py FE-1 FE-2 ...

Salida (incremental):
    verificacion_hibrido_resultado.json — {fe: {encontrado, estado, activity, columnas_nuevas}}
"""
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from toa_client import login_y_obtener_sesion, buscar_y_extraer_fe
from scripts_db.campo_mapper import mapear_activity_a_columnas

SALIDA = Path(__file__).parent.parent / "verificacion_hibrido_resultado.json"


def cargar_resultado_previo():
    if SALIDA.exists():
        return json.loads(SALIDA.read_text(encoding="utf-8"))
    return {}


def guardar(resultado):
    SALIDA.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    fes = sys.argv[1:]
    if not fes:
        print("Uso: python scripts_db/verificar_cliente_hibrido.py FE-1 FE-2 ...")
        sys.exit(1)

    resultado = cargar_resultado_previo()
    pendientes = [fe for fe in fes if fe not in resultado]
    print(f"Total: {len(fes)} | ya procesados: {len(fes) - len(pendientes)} | pendientes: {len(pendientes)}")

    if not pendientes:
        print("Nada pendiente.")
    else:
        print("Login (Playwright, una sola vez)...")
        sesion = login_y_obtener_sesion()
        print("Sesión obtenida. Procesando FEs por HTTP puro...\n")

        for i, fe in enumerate(pendientes, start=1):
            print(f"[{i}/{len(pendientes)}] {fe}...")
            try:
                act = buscar_y_extraer_fe(sesion, fe)
            except Exception as e:
                print(f"  ERROR: {e}")
                resultado[fe] = {"encontrado": False, "error": str(e)}
                guardar(resultado)
                continue

            if act:
                columnas_nuevas = mapear_activity_a_columnas(act)
                resultado[fe] = {
                    "encontrado": True,
                    "estado": act.get("astatus"),
                    "activity": act,
                    "columnas_nuevas_mapeadas": columnas_nuevas,
                }
                print(f"  OK — estado: {act.get('astatus')}, campos activity: {len(act)}, columnas nuevas: {len(columnas_nuevas)}")
            else:
                resultado[fe] = {"encontrado": False}
                print("  no encontrado")

            guardar(resultado)

            if i < len(pendientes):
                espera = random.uniform(8, 20) if random.random() > 0.12 else random.uniform(25, 45)
                time.sleep(espera)

    encontrados = sum(1 for v in resultado.values() if v.get("encontrado"))
    print(f"\nTotal encontrados: {encontrados}/{len(resultado)}")
    print(f"Guardado en: {SALIDA}")


if __name__ == "__main__":
    main()
